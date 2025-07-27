"""数据访问层仓库类"""

import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from shared.models.user import User, CreditTransaction, TransactionType
from shared.models.task import Task, TaskResult
from shared.models.agent import Agent, AgentResource


class BaseRepository:
    """基础仓库类"""
    
    def __init__(self, session: Session):
        self.session = session
    
    async def commit(self):
        """提交事务"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            await self.session.commit()
        else:
            # 同步会话
            self.session.commit()
    
    async def rollback(self):
        """回滚事务"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            await self.session.rollback()
        else:
            # 同步会话
            self.session.rollback()


class UserRepository(BaseRepository):
    """用户仓库类"""
    
    async def create(self, user_data: Dict[str, Any]) -> User:
        """创建用户"""
        user = User(**user_data)
        self.session.add(user)
        if hasattr(self.session, 'execute'):
            # 异步会话 - 刷新但不提交
            await self.session.flush()
        else:
            # 同步会话 - 刷新但不提交
            self.session.flush()
        return user
    
    async def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """根据ID获取用户"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(User).where(User.id == user_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        else:
            # 同步会话
            return self.session.query(User).filter(User.id == user_id).first()
    
    async def get_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(User).where(User.username == username)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        else:
            # 同步会话
            return self.session.query(User).filter(User.username == username).first()
    
    async def get_by_email(self, email: str) -> Optional[User]:
        """根据邮箱获取用户"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(User).where(User.email == email)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        else:
            # 同步会话
            return self.session.query(User).filter(User.email == email).first()
    
    async def get_by_api_key(self, api_key: str) -> Optional[User]:
        """根据API密钥获取用户"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(User).where(User.api_key == api_key)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        else:
            # 同步会话
            return self.session.query(User).filter(User.api_key == api_key).first()
    
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[User]:
        """获取所有用户（分页）"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(User).offset(skip).limit(limit).order_by(User.created_at.desc())
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(User)
                   .order_by(User.created_at.desc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def update(self, user_id: uuid.UUID, update_data: Dict[str, Any]) -> Optional[User]:
        """更新用户"""
        user = await self.get_by_id(user_id)
        if not user:
            return None
        
        for key, value in update_data.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        # 确保更新时间发生变化
        import time
        time.sleep(0.002)  # 确保时间戳不同
        user.updated_at = datetime.utcnow()
        
        if hasattr(self.session, 'execute'):
            # 异步会话 - 刷新但不提交
            await self.session.flush()
            # 刷新对象以获取最新状态
            await self.session.refresh(user)
        else:
            # 同步会话 - 刷新但不提交
            self.session.flush()
            # 刷新对象以获取最新状态
            self.session.refresh(user)
        
        # 返回一个新的查询结果以确保时间戳正确
        return await self.get_by_id(user_id)
    
    async def delete(self, user_id: uuid.UUID) -> bool:
        """删除用户"""
        user = await self.get_by_id(user_id)
        if not user:
            return False
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            await self.session.delete(user)
            await self.session.flush()
        else:
            # 同步会话
            self.session.delete(user)
            self.session.flush()
        
        return True
    
    async def search(self, query: str, skip: int = 0, limit: int = 100) -> List[User]:
        """搜索用户"""
        search_filter = or_(
            User.username.ilike(f"%{query}%"),
            User.email.ilike(f"%{query}%"),
            User.company_name.ilike(f"%{query}%")
        )
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(User)
                   .where(search_filter)
                   .offset(skip)
                   .limit(limit)
                   .order_by(User.created_at.desc()))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(User)
                   .filter(search_filter)
                   .order_by(User.created_at.desc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def count(self) -> int:
        """获取用户总数"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(func.count(User.id))
            result = await self.session.execute(stmt)
            return result.scalar()
        else:
            # 同步会话
            return self.session.query(func.count(User.id)).scalar()
    
    async def get_users_with_low_credits(self, threshold: float = 10.0) -> List[User]:
        """获取点数不足的用户"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(User).where(User.credits < threshold)
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return self.session.query(User).filter(User.credits < threshold).all()
    
    async def get_active_users(self, days: int = 30) -> List[User]:
        """获取活跃用户（最近N天内登录过）"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(User).where(
                and_(
                    User.last_login.isnot(None),
                    User.last_login > cutoff_date
                )
            )
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(User)
                   .filter(
                       and_(
                           User.last_login.isnot(None),
                           User.last_login > cutoff_date
                       )
                   )
                   .all())
    
    async def update_last_login(self, user_id: uuid.UUID) -> bool:
        """更新最后登录时间"""
        user = await self.get_by_id(user_id)
        if not user:
            return False
        
        user.last_login = datetime.utcnow()
        if hasattr(self.session, 'execute'):
            # 异步会话 - 刷新但不提交
            await self.session.flush()
        else:
            # 同步会话 - 刷新但不提交
            self.session.flush()
        return True
    
    async def is_username_taken(self, username: str, exclude_user_id: uuid.UUID = None) -> bool:
        """检查用户名是否已被使用"""
        query_filter = User.username == username
        if exclude_user_id:
            query_filter = and_(query_filter, User.id != exclude_user_id)
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(func.count(User.id)).where(query_filter)
            result = await self.session.execute(stmt)
            return result.scalar() > 0
        else:
            # 同步会话
            return self.session.query(func.count(User.id)).filter(query_filter).scalar() > 0
    
    async def is_email_taken(self, email: str, exclude_user_id: uuid.UUID = None) -> bool:
        """检查邮箱是否已被使用"""
        query_filter = User.email == email
        if exclude_user_id:
            query_filter = and_(query_filter, User.id != exclude_user_id)
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(func.count(User.id)).where(query_filter)
            result = await self.session.execute(stmt)
            return result.scalar() > 0
        else:
            # 同步会话
            return self.session.query(func.count(User.id)).filter(query_filter).scalar() > 0


class CreditTransactionRepository(BaseRepository):
    """点数交易仓库类"""
    
    async def create(self, transaction_data: Dict[str, Any]) -> CreditTransaction:
        """创建交易记录"""
        transaction = CreditTransaction(**transaction_data)
        self.session.add(transaction)
        if hasattr(self.session, 'execute'):
            # 异步会话 - 刷新但不提交
            await self.session.flush()
        else:
            # 同步会话 - 刷新但不提交
            self.session.flush()
        
        # 确保时间戳不同
        import time
        time.sleep(0.001)
        return transaction
    
    async def get_by_id(self, transaction_id: uuid.UUID) -> Optional[CreditTransaction]:
        """根据ID获取交易记录"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(CreditTransaction).where(CreditTransaction.id == transaction_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        else:
            # 同步会话
            return self.session.query(CreditTransaction).filter(CreditTransaction.id == transaction_id).first()
    
    async def get_by_user_id(self, user_id: uuid.UUID, skip: int = 0, limit: int = 100) -> List[CreditTransaction]:
        """获取用户的交易记录"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(CreditTransaction)
                   .where(CreditTransaction.user_id == user_id)
                   .order_by(CreditTransaction.created_at.desc())
                   .offset(skip)
                   .limit(limit))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(CreditTransaction)
                   .filter(CreditTransaction.user_id == user_id)
                   .order_by(CreditTransaction.created_at.desc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def get_by_type(self, transaction_type: TransactionType, skip: int = 0, limit: int = 100) -> List[CreditTransaction]:
        """根据交易类型获取记录"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(CreditTransaction)
                   .where(CreditTransaction.type == transaction_type)
                   .order_by(CreditTransaction.created_at.desc())
                   .offset(skip)
                   .limit(limit))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(CreditTransaction)
                   .filter(CreditTransaction.type == transaction_type)
                   .order_by(CreditTransaction.created_at.desc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def get_user_balance_history(self, user_id: uuid.UUID, days: int = 30) -> List[Dict[str, Any]]:
        """获取用户余额历史"""
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(CreditTransaction)
                   .where(
                       and_(
                           CreditTransaction.user_id == user_id,
                           CreditTransaction.created_at >= cutoff_date
                       )
                   )
                   .order_by(CreditTransaction.created_at.asc()))
            result = await self.session.execute(stmt)
            transactions = result.scalars().all()
        else:
            # 同步会话
            transactions = (self.session.query(CreditTransaction)
                           .filter(
                               and_(
                                   CreditTransaction.user_id == user_id,
                                   CreditTransaction.created_at >= cutoff_date
                               )
                           )
                           .order_by(CreditTransaction.created_at.asc())
                           .all())
        
        # 计算余额历史
        balance_history = []
        running_balance = 0.0
        
        for transaction in transactions:
            running_balance += transaction.amount
            balance_history.append({
                'date': transaction.created_at,
                'amount': transaction.amount,
                'balance': running_balance,
                'type': transaction.type.value,
                'description': transaction.description
            })
        
        return balance_history
    
    async def get_user_total_spent(self, user_id: uuid.UUID, days: int = None) -> float:
        """获取用户总消费"""
        query_filter = and_(
            CreditTransaction.user_id == user_id,
            CreditTransaction.type == TransactionType.CONSUMPTION
        )
        
        if days:
            from datetime import timedelta
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            query_filter = and_(query_filter, CreditTransaction.created_at >= cutoff_date)
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(func.sum(func.abs(CreditTransaction.amount))).where(query_filter)
            result = await self.session.execute(stmt)
            total = result.scalar()
        else:
            # 同步会话
            total = (self.session.query(func.sum(func.abs(CreditTransaction.amount)))
                    .filter(query_filter)
                    .scalar())
        
        return total or 0.0
    
    async def get_user_total_recharged(self, user_id: uuid.UUID, days: int = None) -> float:
        """获取用户总充值"""
        query_filter = and_(
            CreditTransaction.user_id == user_id,
            CreditTransaction.type.in_([TransactionType.RECHARGE, TransactionType.VOUCHER])
        )
        
        if days:
            from datetime import timedelta
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            query_filter = and_(query_filter, CreditTransaction.created_at >= cutoff_date)
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(func.sum(CreditTransaction.amount)).where(query_filter)
            result = await self.session.execute(stmt)
            total = result.scalar()
        else:
            # 同步会话
            total = (self.session.query(func.sum(CreditTransaction.amount))
                    .filter(query_filter)
                    .scalar())
        
        return total or 0.0
    
    async def delete_old_transactions(self, days: int = 365) -> int:
        """删除旧的交易记录"""
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = delete(CreditTransaction).where(CreditTransaction.created_at < cutoff_date)
            result = await self.session.execute(stmt)
            deleted_count = result.rowcount
        else:
            # 同步会话
            deleted_count = (self.session.query(CreditTransaction)
                           .filter(CreditTransaction.created_at < cutoff_date)
                           .delete())
        
        if hasattr(self.session, 'execute'):
            # 异步会话 - 刷新但不提交
            await self.session.flush()
        else:
            # 同步会话 - 刷新但不提交
            self.session.flush()
        return deleted_count


class TaskRepository(BaseRepository):
    """任务仓库类"""
    
    async def create(self, task_data: Dict[str, Any]) -> Task:
        """创建任务"""
        task = Task(**task_data)
        self.session.add(task)
        if hasattr(self.session, 'execute'):
            # 异步会话 - 刷新但不提交
            await self.session.flush()
        else:
            # 同步会话 - 刷新但不提交
            self.session.flush()
        return task
    
    async def get_by_id(self, task_id: uuid.UUID) -> Optional[Task]:
        """根据ID获取任务"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(Task).where(Task.id == task_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        else:
            # 同步会话
            return self.session.query(Task).filter(Task.id == task_id).first()
    
    async def get_by_user_id(self, user_id: uuid.UUID, skip: int = 0, limit: int = 100) -> List[Task]:
        """获取用户的任务列表"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(Task)
                   .where(Task.user_id == user_id)
                   .order_by(Task.created_at.desc())
                   .offset(skip)
                   .limit(limit))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(Task)
                   .filter(Task.user_id == user_id)
                   .order_by(Task.created_at.desc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Task]:
        """获取所有任务（分页）"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(Task).offset(skip).limit(limit).order_by(Task.created_at.desc())
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(Task)
                   .order_by(Task.created_at.desc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def update(self, task_id: uuid.UUID, update_data: Dict[str, Any]) -> Optional[Task]:
        """更新任务"""
        task = await self.get_by_id(task_id)
        if not task:
            return None
        
        for key, value in update_data.items():
            if hasattr(task, key):
                setattr(task, key, value)
        
        # 确保更新时间发生变化
        import time
        time.sleep(0.002)
        task.updated_at = datetime.utcnow()
        
        if hasattr(self.session, 'execute'):
            # 异步会话 - 刷新但不提交
            await self.session.flush()
            # 刷新对象以获取最新状态
            await self.session.refresh(task)
        else:
            # 同步会话 - 刷新但不提交
            self.session.flush()
            # 刷新对象以获取最新状态
            self.session.refresh(task)
        
        # 返回一个新的查询结果以确保时间戳正确
        return await self.get_by_id(task_id)
    
    async def delete(self, task_id: uuid.UUID) -> bool:
        """删除任务"""
        task = await self.get_by_id(task_id)
        if not task:
            return False
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            await self.session.delete(task)
            await self.session.flush()
        else:
            # 同步会话
            self.session.delete(task)
            self.session.flush()
        
        return True
    
    async def get_by_status(self, status: str, skip: int = 0, limit: int = 100) -> List[Task]:
        """根据状态获取任务"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(Task)
                   .where(Task.status == status)
                   .order_by(Task.created_at.desc())
                   .offset(skip)
                   .limit(limit))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(Task)
                   .filter(Task.status == status)
                   .order_by(Task.created_at.desc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def get_active_tasks(self, skip: int = 0, limit: int = 100) -> List[Task]:
        """获取活跃任务"""
        from shared.models.task import TaskStatus
        return await self.get_by_status(TaskStatus.ACTIVE, skip, limit)
    
    async def get_executable_tasks(self, limit: int = 100) -> List[Task]:
        """获取可执行的任务"""
        from shared.models.task import TaskStatus
        current_time = datetime.utcnow()
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(Task)
                   .where(
                       and_(
                           Task.status == TaskStatus.ACTIVE,
                           or_(
                               Task.next_run.is_(None),
                               Task.next_run <= current_time
                           )
                       )
                   )
                   .order_by(Task.priority.desc(), Task.created_at.asc())
                   .limit(limit))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(Task)
                   .filter(
                       and_(
                           Task.status == TaskStatus.ACTIVE,
                           or_(
                               Task.next_run.is_(None),
                               Task.next_run <= current_time
                           )
                       )
                   )
                   .order_by(Task.priority.desc(), Task.created_at.asc())
                   .limit(limit)
                   .all())
    
    async def search(self, query: str, user_id: uuid.UUID = None, skip: int = 0, limit: int = 100) -> List[Task]:
        """搜索任务"""
        search_filter = or_(
            Task.name.ilike(f"%{query}%"),
            Task.description.ilike(f"%{query}%"),
            Task.target.ilike(f"%{query}%")
        )
        
        if user_id:
            search_filter = and_(search_filter, Task.user_id == user_id)
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(Task)
                   .where(search_filter)
                   .offset(skip)
                   .limit(limit)
                   .order_by(Task.created_at.desc()))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(Task)
                   .filter(search_filter)
                   .order_by(Task.created_at.desc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def count(self, user_id: uuid.UUID = None) -> int:
        """获取任务总数"""
        query_filter = None
        if user_id:
            query_filter = Task.user_id == user_id
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(func.count(Task.id))
            if query_filter is not None:
                stmt = stmt.where(query_filter)
            result = await self.session.execute(stmt)
            return result.scalar()
        else:
            # 同步会话
            query = self.session.query(func.count(Task.id))
            if query_filter is not None:
                query = query.filter(query_filter)
            return query.scalar()
    
    async def get_tasks_by_protocol(self, protocol: str, skip: int = 0, limit: int = 100) -> List[Task]:
        """根据协议类型获取任务"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(Task)
                   .where(Task.protocol == protocol)
                   .order_by(Task.created_at.desc())
                   .offset(skip)
                   .limit(limit))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(Task)
                   .filter(Task.protocol == protocol)
                   .order_by(Task.created_at.desc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def get_high_frequency_tasks(self, threshold: int = 60, skip: int = 0, limit: int = 100) -> List[Task]:
        """获取高频任务（频率小于阈值秒数）"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(Task)
                   .where(Task.frequency < threshold)
                   .order_by(Task.frequency.asc())
                   .offset(skip)
                   .limit(limit))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(Task)
                   .filter(Task.frequency < threshold)
                   .order_by(Task.frequency.asc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def update_next_run_batch(self, task_ids: List[uuid.UUID]) -> int:
        """批量更新任务的下次执行时间"""
        if not task_ids:
            return 0
        
        current_time = datetime.utcnow()
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (update(Task)
                   .where(Task.id.in_(task_ids))
                   .values(next_run=current_time))
            result = await self.session.execute(stmt)
            await self.session.flush()
            return result.rowcount
        else:
            # 同步会话
            updated_count = (self.session.query(Task)
                           .filter(Task.id.in_(task_ids))
                           .update({'next_run': current_time}))
            self.session.flush()
            return updated_count
    
    async def pause_tasks_batch(self, task_ids: List[uuid.UUID]) -> int:
        """批量暂停任务"""
        if not task_ids:
            return 0
        
        from shared.models.task import TaskStatus
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (update(Task)
                   .where(Task.id.in_(task_ids))
                   .values(status=TaskStatus.PAUSED, next_run=None))
            result = await self.session.execute(stmt)
            await self.session.flush()
            return result.rowcount
        else:
            # 同步会话
            updated_count = (self.session.query(Task)
                           .filter(Task.id.in_(task_ids))
                           .update({
                               'status': TaskStatus.PAUSED,
                               'next_run': None
                           }))
            self.session.flush()
            return updated_count
    
    async def resume_tasks_batch(self, task_ids: List[uuid.UUID]) -> int:
        """批量恢复任务"""
        if not task_ids:
            return 0
        
        from shared.models.task import TaskStatus
        current_time = datetime.utcnow()
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (update(Task)
                   .where(Task.id.in_(task_ids))
                   .values(status=TaskStatus.ACTIVE, next_run=current_time))
            result = await self.session.execute(stmt)
            await self.session.flush()
            return result.rowcount
        else:
            # 同步会话
            updated_count = (self.session.query(Task)
                           .filter(Task.id.in_(task_ids))
                           .update({
                               'status': TaskStatus.ACTIVE,
                               'next_run': current_time
                           }))
            self.session.flush()
            return updated_count
    
    async def get_user_task_ids(self, user_id: uuid.UUID) -> List[uuid.UUID]:
        """获取用户的所有任务ID"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(Task.id).where(Task.user_id == user_id)
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return [task.id for task in self.session.query(Task.id).filter(Task.user_id == user_id).all()]
    
    async def get_task_statistics(self, start_time: datetime = None, end_time: datetime = None, user_id: uuid.UUID = None) -> Dict[str, Any]:
        """获取任务统计数据"""
        from shared.models.task import TaskStatus, ProtocolType
        
        # 构建基础查询条件
        query_conditions = []
        if user_id:
            query_conditions.append(Task.user_id == user_id)
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            base_stmt = select(Task)
            if query_conditions:
                base_stmt = base_stmt.where(and_(*query_conditions))
            
            # 总任务数
            total_stmt = select(func.count(Task.id))
            if query_conditions:
                total_stmt = total_stmt.where(and_(*query_conditions))
            total_result = await self.session.execute(total_stmt)
            total_tasks = total_result.scalar()
            
            # 按状态统计
            status_stats = {}
            for status in TaskStatus:
                status_stmt = select(func.count(Task.id)).where(Task.status == status)
                if query_conditions:
                    status_stmt = status_stmt.where(and_(*query_conditions))
                status_result = await self.session.execute(status_stmt)
                status_stats[status.value] = status_result.scalar()
            
            # 按协议统计
            protocol_stats = {}
            for protocol in ProtocolType:
                protocol_stmt = select(func.count(Task.id)).where(Task.protocol == protocol)
                if query_conditions:
                    protocol_stmt = protocol_stmt.where(and_(*query_conditions))
                protocol_result = await self.session.execute(protocol_stmt)
                protocol_stats[protocol.value] = protocol_result.scalar()
            
        else:
            # 同步会话
            base_query = self.session.query(Task)
            if query_conditions:
                base_query = base_query.filter(and_(*query_conditions))
            
            total_tasks = base_query.count()
            
            # 按状态统计
            status_stats = {}
            for status in TaskStatus:
                query = base_query.filter(Task.status == status)
                status_stats[status.value] = query.count()
            
            # 按协议统计
            protocol_stats = {}
            for protocol in ProtocolType:
                query = base_query.filter(Task.protocol == protocol)
                protocol_stats[protocol.value] = query.count()
        
        return {
            'total_tasks': total_tasks,
            'status_distribution': status_stats,
            'protocol_distribution': protocol_stats
        }


class TaskResultRepository(BaseRepository):
    """任务结果仓库类"""
    
    async def create(self, result_data: Dict[str, Any]) -> TaskResult:
        """创建任务结果"""
        result = TaskResult(**result_data)
        self.session.add(result)
        if hasattr(self.session, 'execute'):
            # 异步会话 - 刷新但不提交
            await self.session.flush()
        else:
            # 同步会话 - 刷新但不提交
            self.session.flush()
        return result
    
    async def get_by_id(self, result_id: uuid.UUID) -> Optional[TaskResult]:
        """根据ID获取任务结果"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(TaskResult).where(TaskResult.id == result_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        else:
            # 同步会话
            return self.session.query(TaskResult).filter(TaskResult.id == result_id).first()
    
    async def get_by_task_id(self, task_id: uuid.UUID, skip: int = 0, limit: int = 100) -> List[TaskResult]:
        """获取任务的结果列表"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(TaskResult)
                   .where(TaskResult.task_id == task_id)
                   .order_by(TaskResult.execution_time.desc())
                   .offset(skip)
                   .limit(limit))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(TaskResult)
                   .filter(TaskResult.task_id == task_id)
                   .order_by(TaskResult.execution_time.desc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def get_by_agent_id(self, agent_id: uuid.UUID, skip: int = 0, limit: int = 100) -> List[TaskResult]:
        """获取代理的结果列表"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(TaskResult)
                   .where(TaskResult.agent_id == agent_id)
                   .order_by(TaskResult.execution_time.desc())
                   .offset(skip)
                   .limit(limit))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(TaskResult)
                   .filter(TaskResult.agent_id == agent_id)
                   .order_by(TaskResult.execution_time.desc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def get_by_status(self, status: str, skip: int = 0, limit: int = 100) -> List[TaskResult]:
        """根据状态获取结果"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(TaskResult)
                   .where(TaskResult.status == status)
                   .order_by(TaskResult.execution_time.desc())
                   .offset(skip)
                   .limit(limit))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(TaskResult)
                   .filter(TaskResult.status == status)
                   .order_by(TaskResult.execution_time.desc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def get_recent_results(self, hours: int = 24, skip: int = 0, limit: int = 100) -> List[TaskResult]:
        """获取最近的结果"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(TaskResult)
                   .where(TaskResult.execution_time >= cutoff_time)
                   .order_by(TaskResult.execution_time.desc())
                   .offset(skip)
                   .limit(limit))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(TaskResult)
                   .filter(TaskResult.execution_time >= cutoff_time)
                   .order_by(TaskResult.execution_time.desc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def get_task_statistics(self, task_id: uuid.UUID, days: int = 30) -> Dict[str, Any]:
        """获取任务统计信息"""
        from shared.models.task import TaskResultStatus
        cutoff_time = datetime.utcnow() - timedelta(days=days)
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            # 总执行次数
            total_stmt = select(func.count(TaskResult.id)).where(
                and_(
                    TaskResult.task_id == task_id,
                    TaskResult.execution_time >= cutoff_time
                )
            )
            total_result = await self.session.execute(total_stmt)
            total_executions = total_result.scalar()
            
            # 成功次数
            success_stmt = select(func.count(TaskResult.id)).where(
                and_(
                    TaskResult.task_id == task_id,
                    TaskResult.execution_time >= cutoff_time,
                    TaskResult.status == TaskResultStatus.SUCCESS
                )
            )
            success_result = await self.session.execute(success_stmt)
            successful_executions = success_result.scalar()
            
            # 平均响应时间
            avg_stmt = select(func.avg(TaskResult.duration)).where(
                and_(
                    TaskResult.task_id == task_id,
                    TaskResult.execution_time >= cutoff_time,
                    TaskResult.status == TaskResultStatus.SUCCESS,
                    TaskResult.duration.isnot(None)
                )
            )
            avg_result = await self.session.execute(avg_stmt)
            avg_response_time = avg_result.scalar()
            
        else:
            # 同步会话
            base_query = self.session.query(TaskResult).filter(
                and_(
                    TaskResult.task_id == task_id,
                    TaskResult.execution_time >= cutoff_time
                )
            )
            
            total_executions = base_query.count()
            successful_executions = base_query.filter(
                TaskResult.status == TaskResultStatus.SUCCESS
            ).count()
            
            avg_response_time = base_query.filter(
                and_(
                    TaskResult.status == TaskResultStatus.SUCCESS,
                    TaskResult.duration.isnot(None)
                )
            ).with_entities(func.avg(TaskResult.duration)).scalar()
        
        success_rate = (successful_executions / total_executions) if total_executions > 0 else 0.0
        
        return {
            'task_id': task_id,
            'total_executions': total_executions,
            'successful_executions': successful_executions,
            'failed_executions': total_executions - successful_executions,
            'success_rate': success_rate,
            'avg_response_time': avg_response_time
        }
    
    async def get_agent_statistics(self, agent_id: uuid.UUID, days: int = 30) -> Dict[str, Any]:
        """获取代理统计信息"""
        from shared.models.task import TaskResultStatus
        cutoff_time = datetime.utcnow() - timedelta(days=days)
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            # 总执行次数
            total_stmt = select(func.count(TaskResult.id)).where(
                and_(
                    TaskResult.agent_id == agent_id,
                    TaskResult.execution_time >= cutoff_time
                )
            )
            total_result = await self.session.execute(total_stmt)
            total_executions = total_result.scalar()
            
            # 成功次数
            success_stmt = select(func.count(TaskResult.id)).where(
                and_(
                    TaskResult.agent_id == agent_id,
                    TaskResult.execution_time >= cutoff_time,
                    TaskResult.status == TaskResultStatus.SUCCESS
                )
            )
            success_result = await self.session.execute(success_stmt)
            successful_executions = success_result.scalar()
            
            # 平均执行时间
            avg_stmt = select(func.avg(TaskResult.duration)).where(
                and_(
                    TaskResult.agent_id == agent_id,
                    TaskResult.execution_time >= cutoff_time,
                    TaskResult.duration.isnot(None)
                )
            )
            avg_result = await self.session.execute(avg_stmt)
            avg_execution_time = avg_result.scalar()
            
        else:
            # 同步会话
            base_query = self.session.query(TaskResult).filter(
                and_(
                    TaskResult.agent_id == agent_id,
                    TaskResult.execution_time >= cutoff_time
                )
            )
            
            total_executions = base_query.count()
            successful_executions = base_query.filter(
                TaskResult.status == TaskResultStatus.SUCCESS
            ).count()
            
            avg_execution_time = base_query.filter(
                TaskResult.duration.isnot(None)
            ).with_entities(func.avg(TaskResult.duration)).scalar()
        
        success_rate = (successful_executions / total_executions) if total_executions > 0 else 0.0
        
        return {
            'agent_id': agent_id,
            'total_executions': total_executions,
            'successful_executions': successful_executions,
            'failed_executions': total_executions - successful_executions,
            'success_rate': success_rate,
            'avg_execution_time': avg_execution_time
        }
    
    async def delete_old_results(self, days: int = 90) -> int:
        """删除旧的任务结果"""
        cutoff_time = datetime.utcnow() - timedelta(days=days)
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = delete(TaskResult).where(TaskResult.execution_time < cutoff_time)
            result = await self.session.execute(stmt)
            deleted_count = result.rowcount
        else:
            # 同步会话
            deleted_count = (self.session.query(TaskResult)
                           .filter(TaskResult.execution_time < cutoff_time)
                           .delete())
        
        if hasattr(self.session, 'execute'):
            # 异步会话 - 刷新但不提交
            await self.session.flush()
        else:
            # 同步会话 - 刷新但不提交
            self.session.flush()
        return deleted_count
    
    async def count(self, task_id: uuid.UUID = None, agent_id: uuid.UUID = None) -> int:
        """获取结果总数"""
        query_filters = []
        if task_id:
            query_filters.append(TaskResult.task_id == task_id)
        if agent_id:
            query_filters.append(TaskResult.agent_id == agent_id)
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(func.count(TaskResult.id))
            if query_filters:
                stmt = stmt.where(and_(*query_filters))
            result = await self.session.execute(stmt)
            return result.scalar()
        else:
            # 同步会话
            query = self.session.query(func.count(TaskResult.id))
            if query_filters:
                query = query.filter(and_(*query_filters))
            return query.scalar()
    
    async def get_latest_result_by_task(self, task_id: uuid.UUID) -> Optional[TaskResult]:
        """获取任务的最新结果"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(TaskResult)
                   .where(TaskResult.task_id == task_id)
                   .order_by(TaskResult.execution_time.desc())
                   .limit(1))
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        else:
            # 同步会话
            return (self.session.query(TaskResult)
                   .filter(TaskResult.task_id == task_id)
                   .order_by(TaskResult.execution_time.desc())
                   .first())
    
    async def get_failure_results(self, hours: int = 24, skip: int = 0, limit: int = 100) -> List[TaskResult]:
        """获取失败的结果"""
        from shared.models.task import TaskResultStatus
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(TaskResult)
                   .where(
                       and_(
                           TaskResult.execution_time >= cutoff_time,
                           TaskResult.status.in_([TaskResultStatus.ERROR, TaskResultStatus.TIMEOUT])
                       )
                   )
                   .order_by(TaskResult.execution_time.desc())
                   .offset(skip)
                   .limit(limit))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(TaskResult)
                   .filter(
                       and_(
                           TaskResult.execution_time >= cutoff_time,
                           TaskResult.status.in_([TaskResultStatus.ERROR, TaskResultStatus.TIMEOUT])
                       )
                   )
                   .order_by(TaskResult.execution_time.desc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def get_results_with_filters(self, conditions: List = None, skip: int = 0, limit: int = None) -> tuple:
        """根据条件获取结果，支持关联查询"""
        from sqlalchemy.orm import joinedload
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(TaskResult).options(
                joinedload(TaskResult.task),
                joinedload(TaskResult.agent)
            )
            
            if conditions:
                # 如果条件中包含Task表的字段，需要join
                needs_task_join = any('Task.' in str(condition) for condition in conditions)
                if needs_task_join:
                    stmt = stmt.join(Task)
                
                stmt = stmt.where(and_(*conditions))
            
            stmt = stmt.order_by(TaskResult.execution_time.desc())
            
            if skip:
                stmt = stmt.offset(skip)
            if limit:
                stmt = stmt.limit(limit)
            
            result = await self.session.execute(stmt)
            results = result.scalars().all()
            
            # 获取总数
            count_stmt = select(func.count(TaskResult.id))
            if conditions:
                if needs_task_join:
                    count_stmt = count_stmt.join(Task)
                count_stmt = count_stmt.where(and_(*conditions))
            count_result = await self.session.execute(count_stmt)
            total = count_result.scalar()
            
        else:
            # 同步会话
            query = self.session.query(TaskResult).options(
                joinedload(TaskResult.task),
                joinedload(TaskResult.agent)
            )
            
            if conditions:
                # 如果条件中包含Task表的字段，需要join
                needs_task_join = any('Task.' in str(condition) for condition in conditions)
                if needs_task_join:
                    query = query.join(Task)
                
                query = query.filter(and_(*conditions))
            
            query = query.order_by(TaskResult.execution_time.desc())
            
            # 获取总数
            total = query.count()
            
            if skip:
                query = query.offset(skip)
            if limit:
                query = query.limit(limit)
            
            results = query.all()
        
        return results, total
    
    async def get_summary_statistics(self, start_time: datetime = None, end_time: datetime = None, user_id: uuid.UUID = None) -> Dict[str, Any]:
        """获取汇总统计数据"""
        from shared.models.task import TaskResultStatus
        
        # 构建基础查询条件
        query_conditions = []
        if start_time:
            query_conditions.append(TaskResult.execution_time >= start_time)
        if end_time:
            query_conditions.append(TaskResult.execution_time <= end_time)
        
        # 如果指定用户，需要通过任务表关联
        if user_id:
            query_conditions.append(Task.user_id == user_id)
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            base_stmt = select(TaskResult)
            if user_id:
                base_stmt = base_stmt.join(Task)
            if query_conditions:
                base_stmt = base_stmt.where(and_(*query_conditions))
            
            # 总执行次数
            total_stmt = select(func.count(TaskResult.id))
            if user_id:
                total_stmt = total_stmt.join(Task)
            if query_conditions:
                total_stmt = total_stmt.where(and_(*query_conditions))
            total_result = await self.session.execute(total_stmt)
            total_executions = total_result.scalar()
            
            # 成功次数
            success_conditions = query_conditions + [TaskResult.status == TaskResultStatus.SUCCESS]
            success_stmt = select(func.count(TaskResult.id))
            if user_id:
                success_stmt = success_stmt.join(Task)
            success_stmt = success_stmt.where(and_(*success_conditions))
            success_result = await self.session.execute(success_stmt)
            successful_executions = success_result.scalar()
            
            # 平均响应时间
            avg_conditions = query_conditions + [
                TaskResult.status == TaskResultStatus.SUCCESS,
                TaskResult.duration.isnot(None)
            ]
            avg_stmt = select(func.avg(TaskResult.duration))
            if user_id:
                avg_stmt = avg_stmt.join(Task)
            avg_stmt = avg_stmt.where(and_(*avg_conditions))
            avg_result = await self.session.execute(avg_stmt)
            avg_response_time = avg_result.scalar()
            
        else:
            # 同步会话
            base_query = self.session.query(TaskResult)
            if user_id:
                base_query = base_query.join(Task)
            if query_conditions:
                base_query = base_query.filter(and_(*query_conditions))
            
            total_executions = base_query.count()
            successful_executions = base_query.filter(
                TaskResult.status == TaskResultStatus.SUCCESS
            ).count()
            
            avg_response_time = base_query.filter(
                and_(
                    TaskResult.status == TaskResultStatus.SUCCESS,
                    TaskResult.duration.isnot(None)
                )
            ).with_entities(func.avg(TaskResult.duration)).scalar()
        
        success_rate = (successful_executions / total_executions) if total_executions > 0 else 0.0
        
        return {
            'total_executions': total_executions,
            'successful_executions': successful_executions,
            'failed_executions': total_executions - successful_executions,
            'success_rate': success_rate,
            'avg_response_time': avg_response_time or 0.0
        }
    
    async def get_protocol_statistics(self, start_time: datetime = None, end_time: datetime = None, user_id: uuid.UUID = None) -> Dict[str, Any]:
        """获取协议统计数据"""
        from shared.models.task import ProtocolType, TaskResultStatus
        
        # 构建基础查询条件
        query_conditions = []
        if start_time:
            query_conditions.append(TaskResult.execution_time >= start_time)
        if end_time:
            query_conditions.append(TaskResult.execution_time <= end_time)
        if user_id:
            query_conditions.append(Task.user_id == user_id)
        
        protocol_stats = {}
        
        for protocol in ProtocolType:
            protocol_conditions = query_conditions + [Task.protocol == protocol]
            
            if hasattr(self.session, 'execute'):
                # 异步会话
                # 总执行次数
                total_stmt = select(func.count(TaskResult.id)).join(Task).where(and_(*protocol_conditions))
                total_result = await self.session.execute(total_stmt)
                total_executions = total_result.scalar()
                
                # 成功次数
                success_conditions = protocol_conditions + [TaskResult.status == TaskResultStatus.SUCCESS]
                success_stmt = select(func.count(TaskResult.id)).join(Task).where(and_(*success_conditions))
                success_result = await self.session.execute(success_stmt)
                successful_executions = success_result.scalar()
                
                # 平均响应时间
                avg_conditions = protocol_conditions + [
                    TaskResult.status == TaskResultStatus.SUCCESS,
                    TaskResult.duration.isnot(None)
                ]
                avg_stmt = select(func.avg(TaskResult.duration)).join(Task).where(and_(*avg_conditions))
                avg_result = await self.session.execute(avg_stmt)
                avg_response_time = avg_result.scalar()
                
            else:
                # 同步会话
                base_query = self.session.query(TaskResult).join(Task).filter(and_(*protocol_conditions))
                
                total_executions = base_query.count()
                successful_executions = base_query.filter(
                    TaskResult.status == TaskResultStatus.SUCCESS
                ).count()
                
                avg_response_time = base_query.filter(
                    and_(
                        TaskResult.status == TaskResultStatus.SUCCESS,
                        TaskResult.duration.isnot(None)
                    )
                ).with_entities(func.avg(TaskResult.duration)).scalar()
            
            success_rate = (successful_executions / total_executions) if total_executions > 0 else 0.0
            
            protocol_stats[protocol.value] = {
                'total_executions': total_executions,
                'successful_executions': successful_executions,
                'failed_executions': total_executions - successful_executions,
                'success_rate': success_rate,
                'avg_response_time': avg_response_time or 0.0
            }
        
        return protocol_stats


class AgentRepository(BaseRepository):
    """代理仓库类"""
    
    async def create(self, agent_data: Dict[str, Any]) -> Agent:
        """创建代理"""
        agent = Agent(**agent_data)
        self.session.add(agent)
        if hasattr(self.session, 'execute'):
            # 异步会话 - 刷新但不提交
            await self.session.flush()
        else:
            # 同步会话 - 刷新但不提交
            self.session.flush()
        return agent
    
    async def get_by_id(self, agent_id: uuid.UUID) -> Optional[Agent]:
        """根据ID获取代理"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(Agent).where(Agent.id == agent_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        else:
            # 同步会话
            return self.session.query(Agent).filter(Agent.id == agent_id).first()
    
    async def get_by_name(self, name: str) -> Optional[Agent]:
        """根据名称获取代理"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(Agent).where(Agent.name == name)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        else:
            # 同步会话
            return self.session.query(Agent).filter(Agent.name == name).first()
    
    async def get_by_ip_address(self, ip_address: str) -> Optional[Agent]:
        """根据IP地址获取代理"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(Agent).where(Agent.ip_address == ip_address)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        else:
            # 同步会话
            return self.session.query(Agent).filter(Agent.ip_address == ip_address).first()
    
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Agent]:
        """获取所有代理（分页）"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(Agent).offset(skip).limit(limit).order_by(Agent.created_at.desc())
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(Agent)
                   .order_by(Agent.created_at.desc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def update(self, agent_id: uuid.UUID, update_data: Dict[str, Any]) -> Optional[Agent]:
        """更新代理"""
        agent = await self.get_by_id(agent_id)
        if not agent:
            return None
        
        for key, value in update_data.items():
            if hasattr(agent, key):
                setattr(agent, key, value)
        
        # 确保更新时间发生变化
        import time
        time.sleep(0.002)
        agent.updated_at = datetime.utcnow()
        
        if hasattr(self.session, 'execute'):
            # 异步会话 - 刷新但不提交
            await self.session.flush()
            # 刷新对象以获取最新状态
            await self.session.refresh(agent)
        else:
            # 同步会话 - 刷新但不提交
            self.session.flush()
            # 刷新对象以获取最新状态
            self.session.refresh(agent)
        
        # 返回一个新的查询结果以确保时间戳正确
        return await self.get_by_id(agent_id)
    
    async def delete(self, agent_id: uuid.UUID) -> bool:
        """删除代理"""
        agent = await self.get_by_id(agent_id)
        if not agent:
            return False
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            await self.session.delete(agent)
            await self.session.flush()
        else:
            # 同步会话
            self.session.delete(agent)
            self.session.flush()
        
        return True
    
    async def get_by_status(self, status: str, skip: int = 0, limit: int = 100) -> List[Agent]:
        """根据状态获取代理"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(Agent)
                   .where(Agent.status == status)
                   .order_by(Agent.created_at.desc())
                   .offset(skip)
                   .limit(limit))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(Agent)
                   .filter(Agent.status == status)
                   .order_by(Agent.created_at.desc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def get_online_agents(self, skip: int = 0, limit: int = 100) -> List[Agent]:
        """获取在线代理"""
        from shared.models.agent import AgentStatus
        return await self.get_by_status(AgentStatus.ONLINE, skip, limit)
    
    async def get_available_agents(self, skip: int = 0, limit: int = 100) -> List[Agent]:
        """获取可用代理"""
        from shared.models.agent import AgentStatus
        heartbeat_threshold = datetime.utcnow() - timedelta(minutes=5)
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(Agent)
                   .where(
                       and_(
                           Agent.enabled == True,
                           Agent.status.in_([AgentStatus.ONLINE, AgentStatus.BUSY]),
                           Agent.last_heartbeat > heartbeat_threshold
                       )
                   )
                   .order_by(Agent.availability.desc())
                   .offset(skip)
                   .limit(limit))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(Agent)
                   .filter(
                       and_(
                           Agent.enabled == True,
                           Agent.status.in_([AgentStatus.ONLINE, AgentStatus.BUSY]),
                           Agent.last_heartbeat > heartbeat_threshold
                       )
                   )
                   .order_by(Agent.availability.desc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def search(self, query: str, skip: int = 0, limit: int = 100) -> List[Agent]:
        """搜索代理"""
        search_filter = or_(
            Agent.name.ilike(f"%{query}%"),
            Agent.ip_address.ilike(f"%{query}%"),
            Agent.country.ilike(f"%{query}%"),
            Agent.city.ilike(f"%{query}%"),
            Agent.isp.ilike(f"%{query}%")
        )
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(Agent)
                   .where(search_filter)
                   .offset(skip)
                   .limit(limit)
                   .order_by(Agent.created_at.desc()))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(Agent)
                   .filter(search_filter)
                   .order_by(Agent.created_at.desc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def count(self) -> int:
        """获取代理总数"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(func.count(Agent.id))
            result = await self.session.execute(stmt)
            return result.scalar()
        else:
            # 同步会话
            return self.session.query(func.count(Agent.id)).scalar()
    
    async def update_heartbeat(self, agent_id: uuid.UUID) -> bool:
        """更新代理心跳时间"""
        agent = await self.get_by_id(agent_id)
        if not agent:
            return False
        
        from shared.models.agent import AgentStatus
        agent.last_heartbeat = datetime.utcnow()
        if agent.status == AgentStatus.OFFLINE:
            agent.status = AgentStatus.ONLINE
        
        if hasattr(self.session, 'execute'):
            # 异步会话 - 刷新但不提交
            await self.session.flush()
        else:
            # 同步会话 - 刷新但不提交
            self.session.flush()
        return True
    
    async def is_name_taken(self, name: str, exclude_agent_id: uuid.UUID = None) -> bool:
        """检查代理名称是否已被使用"""
        query_filter = Agent.name == name
        if exclude_agent_id:
            query_filter = and_(query_filter, Agent.id != exclude_agent_id)
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(func.count(Agent.id)).where(query_filter)
            result = await self.session.execute(stmt)
            return result.scalar() > 0
        else:
            # 同步会话
            return self.session.query(func.count(Agent.id)).filter(query_filter).scalar() > 0
    
    async def get_agent_statistics(self) -> Dict[str, Any]:
        """获取代理统计数据"""
        from shared.models.agent import AgentStatus
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            # 总代理数
            total_stmt = select(func.count(Agent.id))
            total_result = await self.session.execute(total_stmt)
            total_agents = total_result.scalar()
            
            # 在线代理数
            online_stmt = select(func.count(Agent.id)).where(Agent.status == AgentStatus.ONLINE)
            online_result = await self.session.execute(online_stmt)
            online_agents = online_result.scalar()
            
            # 离线代理数
            offline_stmt = select(func.count(Agent.id)).where(Agent.status == AgentStatus.OFFLINE)
            offline_result = await self.session.execute(offline_stmt)
            offline_agents = offline_result.scalar()
            
            # 忙碌代理数
            busy_stmt = select(func.count(Agent.id)).where(Agent.status == AgentStatus.BUSY)
            busy_result = await self.session.execute(busy_stmt)
            busy_agents = busy_result.scalar()
            
        else:
            # 同步会话
            total_agents = self.session.query(func.count(Agent.id)).scalar()
            online_agents = self.session.query(func.count(Agent.id)).filter(Agent.status == AgentStatus.ONLINE).scalar()
            offline_agents = self.session.query(func.count(Agent.id)).filter(Agent.status == AgentStatus.OFFLINE).scalar()
            busy_agents = self.session.query(func.count(Agent.id)).filter(Agent.status == AgentStatus.BUSY).scalar()
        
        return {
            'total_agents': total_agents,
            'online_agents': online_agents,
            'offline_agents': offline_agents,
            'busy_agents': busy_agents,
            'availability_rate': (online_agents + busy_agents) / total_agents if total_agents > 0 else 0.0
        }


class AgentResourceRepository(BaseRepository):
    """代理资源仓库类"""
    
    async def create(self, resource_data: Dict[str, Any]) -> AgentResource:
        """创建资源记录"""
        resource = AgentResource(**resource_data)
        self.session.add(resource)
        if hasattr(self.session, 'execute'):
            # 异步会话 - 刷新但不提交
            await self.session.flush()
        else:
            # 同步会话 - 刷新但不提交
            self.session.flush()
        return resource
    
    async def get_by_id(self, resource_id: uuid.UUID) -> Optional[AgentResource]:
        """根据ID获取资源记录"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(AgentResource).where(AgentResource.id == resource_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        else:
            # 同步会话
            return self.session.query(AgentResource).filter(AgentResource.id == resource_id).first()
    
    async def get_by_agent_id(self, agent_id: uuid.UUID, skip: int = 0, limit: int = 100) -> List[AgentResource]:
        """获取代理的资源记录"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(AgentResource)
                   .where(AgentResource.agent_id == agent_id)
                   .order_by(AgentResource.timestamp.desc())
                   .offset(skip)
                   .limit(limit))
            result = await self.session.execute(stmt)
            return result.scalars().all()
        else:
            # 同步会话
            return (self.session.query(AgentResource)
                   .filter(AgentResource.agent_id == agent_id)
                   .order_by(AgentResource.timestamp.desc())
                   .offset(skip)
                   .limit(limit)
                   .all())
    
    async def get_latest_by_agent_id(self, agent_id: uuid.UUID) -> Optional[AgentResource]:
        """获取代理的最新资源记录"""
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = (select(AgentResource)
                   .where(AgentResource.agent_id == agent_id)
                   .order_by(AgentResource.timestamp.desc())
                   .limit(1))
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        else:
            # 同步会话
            return (self.session.query(AgentResource)
                   .filter(AgentResource.agent_id == agent_id)
                   .order_by(AgentResource.timestamp.desc())
                   .first())
    
    async def count(self, agent_id: uuid.UUID = None) -> int:
        """获取资源记录总数"""
        query_filter = None
        if agent_id:
            query_filter = AgentResource.agent_id == agent_id
        
        if hasattr(self.session, 'execute'):
            # 异步会话
            stmt = select(func.count(AgentResource.id))
            if query_filter is not None:
                stmt = stmt.where(query_filter)
            result = await self.session.execute(stmt)
            return result.scalar()
        else:
            # 同步会话
            query = self.session.query(func.count(AgentResource.id))
            if query_filter is not None:
                query = query.filter(query_filter)
            return query.scalar()