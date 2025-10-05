"""任务管理服务"""

import asyncio
import logging
import uuid
from datetime import datetime
from datetime import timedelta
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .translation import TranslationService

from ..exceptions import BadRequestException
from ..exceptions import ForbiddenException
from ..exceptions import NotFoundException
from ..models import BatchOperationRequest
from ..models import ErrorDetail
from ..models import StageProgress
from ..models import TaskFilterRequest
from ..models import TaskStatus
from ..models import TranslationProgress
from ..models import TranslationResult
from ..models import TranslationStage
from ..models import TranslationTask
from ..models.enums import TranslationEngine

logger = logging.getLogger(__name__)


class TaskManager:
    """任务管理器"""

    def __init__(self):
        self.tasks: dict[str, TranslationTask] = {}
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.worker_tasks: list[asyncio.Task] = []
        self.max_concurrent_tasks = 10
        self.task_timeout = 3600  # 1小时
        self.cleanup_interval = 300  # 5分钟
        self.translation_service: "TranslationService" | None = None

    async def initialize(self):
        """初始化任务管理器"""
        logger.info("初始化任务管理器")
        # 启动工作进程
        for i in range(self.max_concurrent_tasks):
            worker_task = asyncio.create_task(self._worker(f"worker-{i}"))
            self.worker_tasks.append(worker_task)

        # 启动清理任务
        cleanup_task = asyncio.create_task(self._cleanup_loop())
        self.worker_tasks.append(cleanup_task)

    async def shutdown(self):
        """关闭任务管理器"""
        logger.info("关闭任务管理器")
        # 取消所有工作进程
        for task in self.worker_tasks:
            task.cancel()

        # 等待所有任务完成
        await asyncio.gather(*self.worker_tasks, return_exceptions=True)

    def register_translation_service(self, service: "TranslationService") -> None:
        self.translation_service = service

    async def create_task(
        self, user_id: str, priority: int = 1, estimated_duration: int | None = None
    ) -> TranslationTask:
        """创建新任务"""
        task_id = str(uuid.uuid4())
        now = datetime.now()

        # 初始化进度
        progress = TranslationProgress(
            overall_progress=0.0,
            current_stage=TranslationStage.QUEUED,
            stage_details=[
                StageProgress(
                    stage=TranslationStage.QUEUED,
                    progress=100.0,
                    status="任务已排队",
                    started_at=now,
                    completed_at=now,
                ),
                StageProgress(
                    stage=TranslationStage.PARSING, progress=0.0, status="等待开始"
                ),
                StageProgress(
                    stage=TranslationStage.TRANSLATING, progress=0.0, status="等待开始"
                ),
                StageProgress(
                    stage=TranslationStage.COMPOSING, progress=0.0, status="等待开始"
                ),
            ],
        )

        task = TranslationTask(
            task_id=task_id,
            status=TaskStatus.QUEUED,
            created_at=now,
            updated_at=now,
            progress=progress,
            user_id=user_id,
            priority=priority,
            estimated_duration=estimated_duration,
        )

        # 保存任务
        self.tasks[task_id] = task

        # 添加到队列
        await self.task_queue.put((priority, task_id))

        logger.info(f"创建任务成功: {task_id}, 用户: {user_id}, 优先级: {priority}")
        return task

    async def get_task(self, task_id: str, user_id: str) -> TranslationTask:
        """获取任务"""
        task = self.tasks.get(task_id)
        if not task:
            raise NotFoundException(
                message=f"任务不存在: {task_id}",
                resource="translation_task",
                resource_id=task_id,
            )

        # 检查权限
        if task.user_id != user_id:
            raise ForbiddenException(message=f"无权访问任务: {task_id}")

        return task

    async def update_task_progress(
        self,
        task_id: str,
        stage: TranslationStage,
        progress: float,
        status: str,
        details: dict[str, Any] | None = None,
    ):
        """更新任务进度"""
        task = self.tasks.get(task_id)
        if not task:
            logger.warning(f"尝试更新不存在的任务: {task_id}")
            return

        now = datetime.now()
        task.updated_at = now

        # 更新当前阶段
        task.progress.current_stage = stage
        task.progress.overall_progress = progress

        # 更新阶段详情
        for stage_progress in task.progress.stage_details:
            if stage_progress.stage == stage:
                stage_progress.progress = progress
                stage_progress.status = status
                if details:
                    stage_progress.details = details

                # 设置开始时间
                if progress > 0 and not stage_progress.started_at:
                    stage_progress.started_at = now

                # 设置完成时间
                if progress >= 100 and not stage_progress.completed_at:
                    stage_progress.completed_at = now

                break

        logger.debug(f"更新任务进度: {task_id}, 阶段: {stage}, 进度: {progress}%")

    async def complete_task(self, task_id: str, result: TranslationResult):
        """完成任务"""
        task = self.tasks.get(task_id)
        if not task:
            logger.warning(f"尝试完成不存在的任务: {task_id}")
            return

        now = datetime.now()
        task.status = TaskStatus.COMPLETED
        task.updated_at = now
        task.completed_at = now
        task.progress.overall_progress = 100.0
        task.progress.current_stage = TranslationStage.COMPLETED

        # 更新最后阶段
        for stage_progress in task.progress.stage_details:
            if stage_progress.stage == TranslationStage.COMPOSING:
                stage_progress.progress = 100.0
                stage_progress.status = "翻译完成"
                stage_progress.completed_at = now
                break

        task.result = result

        logger.info(f"任务完成: {task_id}")

    async def fail_task(self, task_id: str, error: ErrorDetail):
        """失败任务"""
        task = self.tasks.get(task_id)
        if not task:
            logger.warning(f"尝试失败不存在的任务: {task_id}")
            return

        now = datetime.now()
        task.status = TaskStatus.FAILED
        task.updated_at = now
        task.completed_at = now

        # 这里可以添加错误处理逻辑
        logger.error(f"任务失败: {task_id}, 错误: {error.message}")

    async def cancel_task(self, task_id: str, user_id: str) -> bool:
        """取消任务"""
        task = await self.get_task(task_id, user_id)

        if task.status in [
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        ]:
            raise BadRequestException(
                message=f"任务 {task_id} 已完成或已失败，无法取消"
            )

        task.status = TaskStatus.CANCELLED
        task.updated_at = datetime.now()

        logger.info(f"任务已取消: {task_id}")
        return True

    async def delete_task(self, task_id: str, user_id: str) -> bool:
        """删除任务"""
        task = await self.get_task(task_id, user_id)

        if task.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            raise BadRequestException(message=f"只能删除已完成或失败的任务: {task_id}")

        # 从任务列表中删除
        del self.tasks[task_id]

        logger.info(f"任务已删除: {task_id}")
        return True

    async def list_tasks(
        self,
        user_id: str,
        filters: TaskFilterRequest,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """列出任务"""
        # 过滤任务
        filtered_tasks = []
        for task in self.tasks.values():
            if task.user_id != user_id:
                continue

            # 应用过滤器
            if filters.status and task.status not in filters.status:
                continue
            if (
                filters.engine
                and task.result
                and task.result.engine_used not in filters.engine
            ):
                continue
            if filters.date_from and task.created_at < filters.date_from:
                continue
            if filters.date_to and task.created_at > filters.date_to:
                continue
            if filters.priority_min and task.priority < filters.priority_min:
                continue
            if filters.priority_max and task.priority > filters.priority_max:
                continue

            filtered_tasks.append(task)

        # 排序（按创建时间降序）
        filtered_tasks.sort(key=lambda x: x.created_at, reverse=True)

        # 分页
        total = len(filtered_tasks)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_tasks = filtered_tasks[start:end]

        total_pages = (total + page_size - 1) // page_size

        return {
            "items": paginated_tasks,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }

    async def batch_operation(
        self, request: BatchOperationRequest, user_id: str
    ) -> dict[str, Any]:
        """批量操作"""
        results = []
        successful = 0
        failed = 0

        for task_id in request.task_ids:
            try:
                if request.operation == "cancel":
                    await self.cancel_task(task_id, user_id)
                elif request.operation == "delete":
                    await self.delete_task(task_id, user_id)
                elif request.operation == "retry":
                    # TODO: 实现重试逻辑
                    pass
                elif request.operation == "pause":
                    # TODO: 实现暂停逻辑
                    pass
                elif request.operation == "resume":
                    # TODO: 实现恢复逻辑
                    pass

                results.append(
                    {
                        "task_id": task_id,
                        "success": True,
                        "message": f"操作 {request.operation} 成功",
                    }
                )
                successful += 1

            except Exception as e:
                results.append(
                    {"task_id": task_id, "success": False, "message": str(e)}
                )
                failed += 1

        return {
            "total_tasks": len(request.task_ids),
            "successful_tasks": successful,
            "failed_tasks": failed,
            "results": results,
        }

    async def get_statistics(self, user_id: str) -> dict[str, Any]:
        """获取任务统计"""
        user_tasks = [task for task in self.tasks.values() if task.user_id == user_id]

        total = len(user_tasks)
        completed = len([t for t in user_tasks if t.status == TaskStatus.COMPLETED])
        failed = len([t for t in user_tasks if t.status == TaskStatus.FAILED])
        processing = len(
            [
                t
                for t in user_tasks
                if t.status
                in [TaskStatus.PARSING, TaskStatus.TRANSLATING, TaskStatus.COMPOSING]
            ]
        )

        # 计算平均处理时间
        completed_tasks = [
            t
            for t in user_tasks
            if t.status == TaskStatus.COMPLETED and t.completed_at and t.started_at
        ]
        avg_processing_time = None
        if completed_tasks:
            processing_times = [
                (t.completed_at - t.started_at).total_seconds() for t in completed_tasks
            ]
            avg_processing_time = sum(processing_times) / len(processing_times)

        # 计算成功率
        success_rate = None
        if total > 0:
            success_rate = completed / total

        return {
            "total_tasks": total,
            "completed_tasks": completed,
            "failed_tasks": failed,
            "processing_tasks": processing,
            "average_processing_time": avg_processing_time,
            "success_rate": success_rate,
        }

    async def _worker(self, worker_id: str):
        """工作进程"""
        logger.info(f"工作进程启动: {worker_id}")

        try:
            while True:
                # 从队列获取任务
                try:
                    priority, task_id = await asyncio.wait_for(
                        self.task_queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                task = self.tasks.get(task_id)
                if not task:
                    logger.warning(f"工作进程 {worker_id} 获取不到任务: {task_id}")
                    continue

                try:
                    await self._process_task(task_id, worker_id)
                except Exception as e:
                    logger.error(f"工作进程 {worker_id} 处理任务 {task_id} 出错: {e}")

        except asyncio.CancelledError:
            logger.info(f"工作进程关闭: {worker_id}")
            raise
        except Exception as e:
            logger.error(f"工作进程 {worker_id} 异常: {e}")
            raise

    async def _process_task(self, task_id: str, worker_id: str):
        """处理任务"""
        logger.info(f"工作进程 {worker_id} 开始处理任务: {task_id}")

        task = self.tasks[task_id]
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()

        try:
            if not self.translation_service:
                raise RuntimeError("Translation service not available")
            await self.translation_service.execute_task(task)
            logger.info(f"工作进程 {worker_id} 完成任务: {task_id}")
        except Exception as exc:
            logger.error(f"任务 {task_id} 执行失败: {exc}")
            error = ErrorDetail(
                code="INTERNAL_ERROR",
                message=str(exc),
                timestamp=datetime.now(),
                retryable=False,
            )
            await self.fail_task(task_id, error)

    async def _cleanup_loop(self):
        """清理循环"""
        try:
            while True:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_old_tasks()
        except asyncio.CancelledError:
            logger.info("清理任务关闭")
            raise

    async def _cleanup_old_tasks(self):
        """清理旧任务"""
        now = datetime.now()
        cutoff_time = now - timedelta(hours=24)  # 24小时前的任务

        tasks_to_remove = []
        for task_id, task in self.tasks.items():
            if (
                task.status
                in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
                and task.completed_at
                and task.completed_at < cutoff_time
            ):
                tasks_to_remove.append(task_id)

        for task_id in tasks_to_remove:
            del self.tasks[task_id]
            logger.info(f"清理旧任务: {task_id}")


# 全局任务管理器实例
task_manager = TaskManager()
