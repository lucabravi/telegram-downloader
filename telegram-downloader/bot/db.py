import logging

from sqlalchemy import Column, Integer, String, DateTime, Boolean, select
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import datetime

Base = declarative_base()


class Chat(Base):
    __tablename__ = 'chat'
    id = Column(Integer, primary_key=True, autoincrement=True)
    current_dir = Column(String, default='.')
    autofolder = Column(Boolean, default=False)
    autoname = Column(Boolean, default=False)
    last_message_id = Column(Integer)
    last_message_date = Column(DateTime, default=datetime.datetime.now)

    @classmethod
    async def update_chat(cls, msg):
        async with async_session() as session:
            chat, create = await get_or_create(cls, id=msg.chat.id)
            chat.last_message_id = msg.id
            chat.last_message_date = datetime.datetime.now()
            await session.commit()
        return chat

    async def update_current_dir(self, current_dir) -> None:
        async with async_session() as session:
            chat = await session.get(Chat, self.id)
            chat.current_dir = current_dir if current_dir != '/' else '.'
            await session.commit()

    async def update_autofolder(self, autofolder) -> None:
        async with async_session() as session:
            chat = await session.get(Chat, self.id)
            chat.autofolder = autofolder
            await session.commit()

    async def update_autoname(self, autoname) -> None:
        async with async_session() as session:
            chat = await session.get(Chat, self.id)
            chat.autoname = autoname
            await session.commit()





async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


engine = create_async_engine('sqlite+aiosqlite:///database_file.db', future=True, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_or_create(model, **kwargs):
    async with async_session() as session:
        try:
            # instance = await session.get(model, **kwargs)
            instance = await session.execute(select(model).filter_by(**kwargs))
            instance = instance.scalars().first()
            if instance is None:
                instance = model(**kwargs)
                session.add(instance)
                await session.commit()
                return instance, True
            return instance, False
        except Exception as e:
            logging.error(f'get_or_create | {e}')
        return None, False
