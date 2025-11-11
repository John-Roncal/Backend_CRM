from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime

# --- Esquemas para el Chat ---

class ChatRequest(BaseModel):
    message: str
    session_id: str # Para mantener la conversación
    user_id: Optional[int] = None # ID del usuario si está logueado

class ChatResponse(BaseModel):
    response: str
    session_id: str

# --- Esquemas para las Herramientas (Function Calling) ---

# Esquema para los datos del perfil alimentario
class PerfilAlimentarioSchema(BaseModel):
    alergias: List[str] = []
    restricciones: List[str] = [] # Ej: "vegano", "vegetariano"
    disgustos: List[str] = []
    gustos: List[str] = []

# Esquema para la herramienta de guardar perfil
class GuardarPerfilSchema(BaseModel):
    nombre: str
    email: EmailStr
    perfil: PerfilAlimentarioSchema

# Esquema para la herramienta de crear reserva
class CrearReservaSchema(BaseModel):
    nombre_reserva: str
    num_comensales: int
    experiencia_id: int
    fecha_hora: datetime
    restricciones_adicionales: Optional[str] = None
    user_id: Optional[int] = None # ID del usuario si ya existe