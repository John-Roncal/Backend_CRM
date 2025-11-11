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
        pass

    def start_chat_session(self, system_prompt: str, history: list = None):

        # El modelo se instancia aquí, para cada sesión, con su prompt de sistema
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
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
            "perfil_alimentario": json.loads(usuario.preferencias.DatosJson) if usuario.preferencias and usuario.preferencias.DatosJson else "Sin perfil.",
            "historial_reservas": [
                {
                    "fecha": r.FechaHora, 
                    "experiencia_id": r.ExperienciaId, 
                    "estado": r.Estado
                } for r in usuario.reservas if r.Estado == 'completada'
            ]
        }
        return contexto

    def _convert_to_dict(self, obj):
        """
        Convierte objetos de Gemini (MapComposite, RepeatedComposite, etc.) a diccionarios Python nativos.
        """
        # MapComposite de proto.marshal (Google)
        if hasattr(obj, 'items') and callable(obj.items):
            return {k: self._convert_to_dict(v) for k, v in obj.items()}
        # Diccionarios normales
        elif isinstance(obj, dict):
            return {k: self._convert_to_dict(v) for k, v in obj.items()}
        # Listas y tuplas
        elif isinstance(obj, (list, tuple)):
            return [self._convert_to_dict(item) for item in obj]
        # RepeatedComposite (lista de protobuf)
        elif hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes, dict)):
            try:
                # Intentar convertir como lista
                return [self._convert_to_dict(item) for item in obj]
            except:
                # Si falla, intentar como objeto con atributos
                pass
        # Objetos protobuf con DESCRIPTOR
        if hasattr(obj, 'DESCRIPTOR'):
            result = {}
            for field in obj.DESCRIPTOR.fields:
                value = getattr(obj, field.name)
                result[field.name] = self._convert_to_dict(value)
            return result
        # Tipos primitivos (str, int, float, bool, None)
        return obj

    async def handle_guardar_perfil(self, db: AsyncSession, user_id: int, args: dict) -> dict:
        """Lógica para la herramienta 'guardar_perfil_alimentario'.
           Recibe el user_id desde main.py, no desde la IA."""
        try:
            perfil_data = args.get('perfil_json', {})
            
            print(f"📋 Perfil recibido (tipo: {type(perfil_data)}): {perfil_data}")
            
            # ✅ CORRECCIÓN: Convertir MapComposite/RepeatedComposite a dict nativo de Python
            perfil_data_dict = self._convert_to_dict(perfil_data)
            
            print(f"📋 Perfil convertido (tipo: {type(perfil_data_dict)}): {perfil_data_dict}")
            
            # Si la conversión falló y es una lista, intentar convertir manualmente
            if isinstance(perfil_data_dict, list):
                print("⚠️ La conversión devolvió una lista, intentando conversión directa...")
                # Convertir el MapComposite directamente a dict
                perfil_data_dict = dict(perfil_data)
                print(f"📋 Conversión directa: {perfil_data_dict}")
            
            # Validar que tengamos un diccionario
            if not isinstance(perfil_data_dict, dict):
                return {
                    "status": "error",
                    "message": f"Error: El perfil no se pudo convertir a diccionario. Tipo recibido: {type(perfil_data_dict)}"
                }
            
            if not perfil_data_dict or all(not v for v in perfil_data_dict.values()):
                return {
                    "status": "info",
                    "message": "No se guardó el perfil porque no se proporcionaron datos válidos de preferencias."
                }

            # Cargar el usuario con su preferencia (si existe)
            result = await db.execute(
                select(models.Usuario).options(joinedload(models.Usuario.preferencias))
                .where(models.Usuario.Id == user_id)
            )
            usuario = result.scalars().first()

            if not usuario:
                return {"status": "error", "message": f"Error crítico: El usuario con ID {user_id} no existe."}

            # Ahora sí podemos serializar a JSON
            perfil_json_str = json.dumps(perfil_data_dict, ensure_ascii=False)
            print(f"💾 JSON a guardar: {perfil_json_str}")

            # ✅ CORRECCIÓN: Usar datetime.utcnow() en lugar de func.now()
            ahora = datetime.utcnow()

            if usuario.preferencias:
                # Actualizar preferencia existente
                usuario.preferencias.DatosJson = perfil_json_str
                usuario.preferencias.ActualizadoEn = ahora
                print(f"✅ Actualizando preferencia existente para usuario {user_id}")
            else:
                # Crear nueva preferencia
                nueva_preferencia = models.Preferencia(
                    UsuarioId=user_id,
                    DatosJson=perfil_json_str,
                    CreadoEn=ahora
                )
                db.add(nueva_preferencia)
                print(f"✅ Creando nueva preferencia para usuario {user_id}")

            # Commit de los cambios
            await db.commit()
            
            # Verificar que se guardó correctamente
            result_check = await db.execute(
                select(models.Preferencia).where(models.Preferencia.UsuarioId == user_id)
            )
            preferencia_guardada = result_check.scalars().first()
            
            if preferencia_guardada:
                print(f"✅ Preferencia confirmada en BD: ID={preferencia_guardada.Id}, Datos={preferencia_guardada.DatosJson}")
            else:
                print(f"⚠️ Advertencia: No se encontró la preferencia después del commit")
            
            return {
                "status": "exito", 
                "message": f"Perfil alimentario guardado exitosamente para el usuario {user_id}.",
                "user_id": user_id
            }

        except Exception as e:
            await db.rollback()
            traceback.print_exc()
            print(f"❌ Error en handle_guardar_perfil: {e}")
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