from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Float, ForeignKey, DECIMAL, Text,
    Identity
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base

class Usuario(Base):
    __tablename__ = 'Usuarios'
    __table_args__ = {'schema': 'dbo'}

    Id = Column(Integer, Identity(), primary_key=True)
    Nombre = Column(String(150), nullable=False)
    Email = Column(String(256), nullable=False, unique=True)
    PasswordHash = Column(String(400))
    Rol = Column(String(20), nullable=False, default='Cliente')
    EmailConfirmado = Column(Boolean, nullable=False, default=False)
    CreadoEn = Column(DateTime, nullable=False, default=func.now())
    ActualizadoEn = Column(DateTime, onupdate=func.now())
    FirebaseUid = Column(String(200))

    preferencias = relationship("Preferencia", back_populates="usuario", uselist=False)
    reservas = relationship("Reserva", back_populates="usuario")

class Experiencia(Base):
    __tablename__ = 'Experiencias'
    __table_args__ = {'schema': 'dbo'}

    Id = Column(Integer, Identity(), primary_key=True)
    Codigo = Column(String(10), nullable=False)
    Nombre = Column(String(250), nullable=False)
    DuracionMinutos = Column(Integer)
    Descripcion = Column(String(1000))
    Precio = Column(DECIMAL(10, 2))
    Activa = Column(Boolean, nullable=False, default=True)
    CreadoEn = Column(DateTime, nullable=False, default=func.now())

class Reserva(Base):
    __tablename__ = 'Reservas'
    __table_args__ = {'schema': 'dbo'}

    Id = Column(Integer, Identity(), primary_key=True)
    UsuarioId = Column(Integer, ForeignKey('dbo.Usuarios.Id', ondelete="SET NULL"))
    NombreReserva = Column(String(150), nullable=False)
    NumComensales = Column(Integer, nullable=False, default=1)
    ExperienciaId = Column(Integer, ForeignKey('dbo.Experiencias.Id'), nullable=False)
    Restricciones = Column(String(500))
    FechaHora = Column(DateTime, nullable=False)
    Estado = Column(String(30), nullable=False, default='pendiente')
    CreadoEn = Column(DateTime, nullable=False, default=func.now()) # <-- COLUMNA AÑADIDA
    ActualizadoEn = Column(DateTime, onupdate=func.now()) # <-- COLUMNA AÑADIDA
    
    usuario = relationship("Usuario", back_populates="reservas")
    experiencia = relationship("Experiencia")

class Preferencia(Base):
    __tablename__ = 'Preferencias'
    __table_args__ = {'schema': 'dbo'}

    Id = Column(Integer, Identity(), primary_key=True)
    UsuarioId = Column(Integer, ForeignKey('dbo.Usuarios.Id', ondelete="CASCADE"), nullable=False)
    DatosJson = Column(Text, nullable=True)
    CreadoEn = Column(DateTime, nullable=False, default=func.now())
    ActualizadoEn = Column(DateTime, onupdate=func.now())
    
    usuario = relationship("Usuario", back_populates="preferencias")