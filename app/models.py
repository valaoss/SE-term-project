from sqlalchemy import Column, Integer, String
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    role = Column(String, nullable=False) # "instructor" veya "student"
    name = Column(String, nullable=True)
    google_sub = Column(String, unique=True, nullable=True)