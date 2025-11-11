import json
import traceback
import google.generativeai.types as genai_types
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Optional

from database import get_db_session
import schemas
import services

app = FastAPI(
    title="CRM Sensorial - Central Restaurante",
    description="Backend para el chatbot de reservas con Gemini"
)

# --- Manejador de Excepciones Global ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Captura cualquier excepción no controlada, la imprime en consola
    y devuelve una respuesta JSON estandarizada.
    """
    # Imprimir el traceback completo en la consola para debugging
    traceback.print_exc()

    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": f"Ocurrió un error interno inesperado: {exc}",
            "traceback": traceback.format_exc()
        },
    )

# --- Configuración de CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https*://localhost:7121",
        "http://localhost:5123",
        "https://localhost:44327",
    ], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Servicios ---
gemini_service = services.GeminiService()
db_service = services.DBService()

# --- Almacenamiento simple de sesiones de chat en memoria ---
# (En producción, considera usar Redis para esto)
chat_sessions: Dict[str, any] = {} 
system_prompts_cache: Dict[str, str] = {} # Cache para los prompts de sistema

async def get_system_prompt(db: AsyncSession, user_id: int) -> str:
    """
    Construye el prompt de sistema.
    Detecta si el usuario tiene un perfil de preferencias
    y da instrucciones a la IA para que actúe proactivamente.
    """
    
    # 1. Cargar las experiencias
    experiencias_contexto = await db_service.get_all_experiences(db)
    
    base_prompt = (
        "Eres 'Amigo Central', el asistente de IA del restaurante Central. "
        "Tu objetivo es ayudar a los clientes principalmente en hacer una reserva y entender sus preferencias sensoriales, pero puedes responder otras preguntas relacionadas con el restaurante. "
        "Eres amable, profesional y conocedor de la alta cocina. "
        "NUNCA inventes una experiencia. Solo existen las 3 que te doy."
        f"{experiencias_contexto}"
    )
    print(experiencias_contexto)

    # 2. Obtener contexto del usuario
    user_contexto = await db_service.get_user_context(db, user_id)
    print(user_contexto)

    # 3. VERIFICAR SI EL PERFIL EXISTE
    perfil_existente = None
    if user_contexto and user_contexto.get('perfil_alimentario') and user_contexto['perfil_alimentario'] != "Sin perfil.":
        perfil_existente = user_contexto['perfil_alimentario']

    # --- INSTRUCCIONES PARA IA ---

    if perfil_existente:
        # --- PROMPT PARA CLIENTE QUE REGRESA (con perfil) ---
        prompt = (
            f"{base_prompt}\n"
            "--- CONTEXTO DEL CLIENTE ---\n"
            f"Estás hablando con {user_contexto['usuario']['nombre']} (ID: {user_contexto['usuario']['id']}).\n"
            f"Este cliente YA TIENE un perfil alimentario guardado: {json.dumps(perfil_existente)}\n"
            f"Historial de visitas: {json.dumps(user_contexto.get('historial_reservas', []))}\n"
            "--- TUS TAREAS ---\n"
            "1. Saluda al cliente por su nombre.\n"
            "2. **PROACTIVAMENTE**, confirma su perfil. Di algo como: 'Veo que en tu perfil guardado tienes [menciona una alergia/restricción clave]. ¿Usamos este perfil para tu visita o hay algún cambio?'\n"
            "3. Si el cliente menciona CUALQUIER cambio (ej: 'hoy no como carne', 'además soy alérgico a X'), **debes actualizar su perfil**.\n"
            "4. Para actualizar, primero recolecta TODA la información (alergias, gustos, etc.) y luego llama a `guardar_perfil_alimentario` con el perfil COMPLETO y ACTUALIZADO. Haz esto **automáticamente** sin que el usuario te lo pida.\n"
            "5. Guíalo para elegir una experiencia, fecha, hora y número de comensales.\n"
            "6. Al final, llama a `crear_reserva`."
        )
    else:
        # --- PROMPT PARA CLIENTE NUEVO (o sin perfil) ---
        nombre_cliente = user_contexto['usuario']['nombre'] if user_contexto else 'cliente'
        cliente_id = user_contexto['usuario']['id'] if user_contexto else user_id
        
        prompt = (
            f"{base_prompt}\n"
            "--- CONTEXTO DEL CLIENTE ---\n"
            f"Estás hablando con {nombre_cliente} (ID: {cliente_id}).\n"
            "Este cliente **NO TIENE** un perfil alimentario guardado. Es su primera vez o nunca lo ha configurado.\n"
            "--- TUS TAREAS ---\n"
            "1. Saluda al cliente por su nombre.\n"
            "2. **PROACTIVAMENTE**, explícale que te gustaría crear su 'perfil sensorial' para darle el mejor servicio. Di algo como: 'Para que tu experiencia sea perfecta, me gustaría hacerte unas preguntas sobre tus preferencias alimentarias.'\n"
            "3. **Debes** preguntar por: (Alergias, Restricciones (vegano, etc.), Disgustos, Gustos).\n"
            "4. Una vez que tengas esta información, **llama automáticamente** a la función `guardar_perfil_alimentario`. No esperes a que el usuario te lo pida.\n"
            "5. Después de guardar, guíalo para elegir una experiencia, fecha, hora y número de comensales.\n"
            "6. Al final, llama a `crear_reserva`."
        )
        
    return prompt

@app.post("/chat", response_model=schemas.ChatResponse)
async def chat_endpoint(
    request: schemas.ChatRequest,
    db: AsyncSession = Depends(get_db_session)
):
    session_id = request.session_id
    user_message = request.message
    
    # IMPORTANTE: Capturamos el user_id de la solicitud
    # Ya hemos securizado el C# para que esto NUNCA sea nulo
    session_user_id = request.user_id 
    if not session_user_id:
         raise HTTPException(status_code=401, detail="Usuario no autenticado.")

    # 1. Obtener o crear la sesión de chat
    if session_id not in chat_sessions:
        # Pasamos el user_id para generar el prompt correcto
        system_prompt = await get_system_prompt(db, session_user_id)
        chat_sessions[session_id] = gemini_service.start_chat_session(system_prompt)
        
    chat_session = chat_sessions[session_id]
    
    # 2. Enviar el mensaje del usuario a Gemini
    try:
        response = await chat_session.send_message_async(user_message)
        
        # 3. Manejar la respuesta (puede ser texto o una llamada a función)
        while response.parts[0].function_call:
            function_call = response.parts[0].function_call
            function_name = function_call.name
            args = dict(function_call.args)
            
            function_response_content = None
            
            # 4. Ejecutar la función correspondiente
            if function_name == "guardar_perfil_alimentario":
                # --- CAMBIO AQUÍ ---
                # Pasamos el session_user_id (de la solicitud) y los args (de la IA)
                tool_result = await db_service.handle_guardar_perfil(db, session_user_id, args)
                # ... (lógica de actualizar prompt si es necesario)
                function_response_content = tool_result

            elif function_name == "crear_reserva":
                # --- CAMBIO AQUÍ ---
                # Pasamos el session_user_id (de la solicitud) y los args (de la IA)
                tool_result = await db_service.handle_crear_reserva(db, session_user_id, args)
                function_response_content = tool_result
            
            if function_response_content is None:
                raise HTTPException(status_code=400, detail=f"Función desconocida: {function_name}")

            # 5. Enviar el resultado de la función de vuelta a Gemini
            response = await chat_session.send_message_async(
                genai_types.Part.from_function_response(
                    name=function_name,
                    response=function_response_content
                )
            )
        
        # 6. La respuesta final
        try:
            final_text_response = response.text
        except ValueError:
            # Esto ocurre si la respuesta final de Gemini es una llamada a función
            # en lugar de texto. Devolvemos un mensaje genérico para que el usuario
            # pueda intentarlo de nuevo.
            final_text_response = "Tuve un problema para procesar la respuesta. Por favor, intenta de nuevo."

        return schemas.ChatResponse(response=final_text_response, session_id=session_id)

    except Exception as e:
        # El manejador global capturará esto, pero lo dejamos por si acaso
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error en chat_endpoint: {str(e)}")

@app.get("/")
def read_root():
    return {"status": "CRM Sensorial Backend - OK"}