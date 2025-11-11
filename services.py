import google.generativeai as genai
import json
import traceback
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from datetime import datetime
import models
import schemas
from database import settings
from tools import chatbot_tools

# Configurar el cliente de Gemini
genai.configure(api_key=settings.GOOGLE_API_KEY)

class GeminiService:
    def __init__(self):
        """
        El modelo ahora se inicializará dinámicamente en `start_chat_session`
        para poder inyectar el system_prompt específico de la sesión.
        """
        pass

    def start_chat_session(self, system_prompt: str, history: list = None):
        """
        Inicia una nueva sesión de chat, creando un modelo con el
        prompt de sistema específico para esa sesión.
        """

        # El modelo se instancia aquí, para cada sesión, con su prompt de sistema
        model = genai.GenerativeModel(
            model_name="gemini-1.5-pro-latest",
            system_instruction=system_prompt,  # Inyecta el contexto y las reglas aquí
            tools=[chatbot_tools]
        )

        chat_history = []
        if history:
            for msg in history:
                chat_history.append({"role": msg["role"], "parts": [msg["parts"]]})

        return model.start_chat(
            history=chat_history,
            enable_automatic_function_calling=False # Control manual
        )

    async def generate_response(self, chat_session, user_message: str):
        """Envía un mensaje y obtiene la respuesta, manejando function calling."""

        response = await chat_session.send_message_async(user_message)
        
        return response

class DBService:
    
    async def get_all_experiences(self, db: AsyncSession) -> str:
        """Obtiene las 3 experiencias de la BD para dárselas al chatbot como contexto."""
        result = await db.execute(select(models.Experiencia).where(models.Experiencia.Activa == True))
        experiencias = result.scalars().all()
        
        experiencias_texto = "\n\n--- EXPERIENCIAS DISPONIBLES ---\n"
        for exp in experiencias:
            experiencias_texto += f"ID: {exp.Id}\n"
            experiencias_texto += f"Nombre: {exp.Nombre}\n"
            experiencias_texto += f"Descripción: {exp.Descripcion}\n"
            experiencias_texto += f"Precio: S/ {exp.Precio}\n"
            experiencias_texto += "---\n"
        return experiencias_texto

    async def get_user_context(self, db: AsyncSession, user_id: int) -> dict:
        """Obtiene los datos del usuario, su perfil y su historial para el contexto."""
        if not user_id:
            return None
        
        result = await db.execute(
            select(models.Usuario)
            .options(
                joinedload(models.Usuario.preferencias),
                joinedload(models.Usuario.reservas)
            )
            .where(models.Usuario.Id == user_id)
        )
        usuario = result.scalars().first()

        if not usuario:
            return None
        
        # Formatear el contexto para el prompt
        contexto = {
            "usuario": {"id": usuario.Id, "nombre": usuario.Nombre, "email": usuario.Email},
            "perfil_alimentario": json.loads(usuario.preferencias.DatosJson) if usuario.preferencias else "Sin perfil.",
            "historial_reservas": [
                {
                    "fecha": r.FechaHora, 
                    "experiencia_id": r.ExperienciaId, 
                    "estado": r.Estado
                } for r in usuario.reservas if r.Estado == 'completada'
            ]
        }
        return contexto


    async def handle_guardar_perfil(self, db: AsyncSession, user_id: int, args: dict) -> dict:
        """Lógica para la herramienta 'guardar_perfil_alimentario'.
           Recibe el user_id desde main.py, no desde la IA."""
        try:
            # --- VALIDACIÓN ---
            # 1. Verificar que el usuario realmente existe
            result_user = await db.execute(select(models.Usuario).where(models.Usuario.Id == user_id))
            usuario = result_user.scalars().first()
            if not usuario:
                return {"status": "error", "message": f"Error crítico: El usuario con ID {user_id} no existe."}
            # --- FIN VALIDACIÓN ---

            perfil_data = args.get('perfil_json', {})

            # --- VALIDACIÓN ADICIONAL ---
            # 2. Verificar que el perfil no esté vacío
            if not perfil_data or not any(perfil_data.values()):
                return {
                    "status": "info",
                    "message": "No se guardó el perfil porque no se proporcionaron datos de preferencias."
                }
            # --- FIN VALIDACIÓN ADICIONAL ---
            
            result_prefs = await db.execute(
                select(models.Preferencia).where(models.Preferencia.UsuarioId == user_id)
            )
            preferencia = result_prefs.scalars().first()
            
            perfil_json_str = json.dumps(perfil_data)

            if preferencia:
                preferencia.DatosJson = perfil_json_str
                preferencia.ActualizadoEn = func.now()
            else:
                preferencia = models.Preferencia(
                    UsuarioId=user_id,
                    DatosJson=perfil_json_str
                )
                db.add(preferencia)
                
            await db.commit()
            
            return {
                "status": "exito", 
                "message": f"Perfil alimentario guardado para el usuario {user_id}.",
                "user_id": user_id
            }

        except Exception as e:
            await db.rollback()
            traceback.print_exc()
            return {"status": "error", "message": f"Error en handle_guardar_perfil: {e}"}

    async def handle_crear_reserva(self, db: AsyncSession, user_id: int, args: dict) -> dict:
        """Lógica para la herramienta 'crear_reserva'.
           Recibe el user_id desde main.py, no desde la IA."""
        try:
            if not user_id:
                return {"status": "error", "message": "Error interno: No se pudo identificar al usuario."}

            experiencia_id = args.get('experiencia_id')

            # --- VALIDACIÓN ---
            # 1. Verificar que el experiencia_id existe
            if experiencia_id:
                result = await db.execute(
                    select(models.Experiencia).where(models.Experiencia.Id == experiencia_id)
                )
                experiencia = result.scalars().first()
                if not experiencia:
                    return {
                        "status": "error",
                        "message": f"El ID de experiencia {experiencia_id} no es válido. Los IDs válidos son 1, 2 o 3. Por favor, pregunta de nuevo al usuario."
                    }
            else:
                return {"status": "error", "message": "El campo 'experiencia_id' es obligatorio."}
            # --- FIN VALIDACIÓN ---

            fecha_hora_dt = datetime.fromisoformat(args['fecha_hora'])

            nueva_reserva = models.Reserva(
                UsuarioId=user_id,
                NombreReserva=args['nombre_reserva'],
                NumComensales=args['num_comensales'],
                ExperienciaId=experiencia_id,
                FechaHora=fecha_hora_dt,
                Restricciones=args.get('restricciones_adicionales'),
                Estado='pendiente'
            )
            
            db.add(nueva_reserva)
            await db.commit()
            await db.refresh(nueva_reserva)
            
            return {
                "status": "exito",
                "message": f"Reserva creada con éxito. ID de reserva: {nueva_reserva.Id}.",
                "reserva_id": nueva_reserva.Id
            }
        
        except Exception as e:
            await db.rollback()
            traceback.print_exc()
            return {"status": "error", "message": f"Error en handle_crear_reserva: {e}"}