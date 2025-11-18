from google.generativeai.types import FunctionDeclaration, Tool

# 1. Herramienta para guardar/actualizar el perfil
guardar_perfil_alimentario = FunctionDeclaration(
    name="guardar_perfil_alimentario",
    description="Guarda o actualiza el perfil alimentario (alergias, gustos, disgustos, restricciones) del usuario logueado.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "alergias": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "Lista de alergias declaradas por el usuario (ej: 'nueces', 'mariscos')."
            },
            "restricciones": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "Lista de restricciones dietéticas (ej: 'vegano', 'sin gluten')."
            },
            "disgustos": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "Lista de ingredientes que no le gustan al usuario."
            },
            "gustos": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "Lista de ingredientes o sabores que le gustan al usuario."
            }
        }
    }
)

# 2. Herramienta para crear la reserva
crear_reserva = FunctionDeclaration(
    name="crear_reserva",
    description="Guarda una nueva reserva en la base de datos para el usuario logueado.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "nombre_reserva": {
                "type": "STRING",
                "description": "Nombre a quien quedará la reserva (puede ser el nombre del usuario)."
            },
            "num_comensales": {
                "type": "INTEGER",
                "description": "Número total de personas en la reserva."
            },
            "experiencia_id": {
                "type": "INTEGER",
                "description": "El ID de la experiencia seleccionada (1, 2 o 3)."
            },
            "fecha_hora": {
                "type": "STRING",
                "description": "Fecha y hora de la reserva en formato ISO 8601 (YYYY-MM-DDTHH:MM:SS)."
            },
            "restricciones_adicionales": {
                "type": "STRING",
                "description": "Observaciones o restricciones específicas para ESTA reserva."
            }
        },
        "required": ["nombre_reserva", "num_comensales", "experiencia_id", "fecha_hora"]
    }
)

# 3. Herramienta para obtener una recomendación de experiencia
recomendar_experiencia = FunctionDeclaration(
    name="recomendar_experiencia",
    description="Cuando el usuario pida una recomendación o no sepa qué elegir, esta herramienta recopila sus preferencias para poder sugerirle la mejor experiencia.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "motivo_visita": {
                "type": "STRING",
                "description": "¿Qué te trae hoy a Central? (Celebración Especial, Negocios, Turismo, Otros)"
            },
            "acompanantes": {
                "type": "STRING",
                "description": "¿Con quién vienes? (Solo, Pareja, Familia, Amigos)"
            },
            "estilo_cocina": {
                "type": "STRING",
                "description": "¿Qué estilo de cocina te atrae más? (Tradicional/Criolla, Moderna/Fusión, Vegana, Gourmet)"
            }
        },
        "required": ["motivo_visita", "acompanantes", "estilo_cocina"]
    }
)

# Lista de herramientas para el modelo
chatbot_tools = Tool(function_declarations=[guardar_perfil_alimentario, crear_reserva, recomendar_experiencia])