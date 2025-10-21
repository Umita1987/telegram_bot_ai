from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, Text, ForeignKey, Float, DateTime, BigInteger
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship
from logs import get_logger
logger = get_logger("models")

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger , primary_key=True)
    username = Column(String, nullable=False)
    is_premium = Column(Boolean, default=False)

    # Связь с таблицей Post
    posts = relationship('Post', back_populates='user')

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', is_premium={self.is_premium})>"


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    content = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)
    link = Column(String, nullable=True)
    short_url = Column(String, nullable=True)  # Новое поле для хранения короткой ссылки Bit.ly
    status = Column(Text, nullable=False, default='draft')
    price = Column(String, nullable=True)
    telegram_message_id = Column(Integer, nullable=True)  # Сохраняем ID сообщения в канале
    published_at = Column(DateTime(timezone=True), nullable=True)  # Дата публикации
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)  # Дата создания

    user = relationship("User", back_populates="posts")
    payments = relationship("Payment", back_populates="post")
    click_stats = relationship("ClickStat", back_populates="post")

    def __repr__(self):
        return (f"<Post(id={self.id}, user_id={self.user_id}, content='{self.content}', "
                f"description='{self.description}', image_url='{self.image_url}', "
                f"link='{self.link}', short_url='{self.short_url}', status='{self.status}', price='{self.price}')>")



class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    post_id = Column(Integer, ForeignKey("posts.id"))
    payment_id = Column(String, unique=True)  # ID из YooKassa
    amount = Column(Float)
    status = Column(String, default="pending")
    invoice_message_id = Column(String, unique=True)

    post = relationship("Post", back_populates="payments")
    user = relationship("User")

    def __repr__(self):
        return (f"<Payment(id={self.id}, user_id={self.user_id}, post_id={self.post_id}, "
                f"payment_id='{self.payment_id}', amount={self.amount}, status='{self.status}')>")


# Новая модель для кликов
class ClickStat(Base):
    __tablename__ = "click_stats"
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    clicked_at = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

    post = relationship("Post", back_populates="click_stats")
