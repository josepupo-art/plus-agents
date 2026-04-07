import os
import json
import re
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Any, Dict, Optional, List

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv(r"C:\plus-agents\.env")


class Config:
    STATE_FILE = os.getenv("STATE_FILE", "secrets/session_state.json")

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

    PRICE_PDF_URL = "https://drive.google.com/file/d/14HdC6fDy0LGY8q11ZNhHz1-NNmOD30sa/view?usp=sharing"
    PRICE_PDF_LABEL = "📄 Lista de precios Marzo 2026 - Plus Aligners (PDF)"

    PHOTO_GUIDE_URL = "https://drive.google.com/file/d/1oE6RpAqPuMAoMJjQYAxt-aLiF5OAVM58/view?usp=sharing"
    PHOTO_GUIDE_LABEL = "📸 Guía de fotos clínicas - Plus Aligners"

    WORKFLOW_URL = "https://drive.google.com/file/d/1FM_Ydxv9U4YSVktNNoiL7Xp0J0YoRTjr/view?usp=sharing"
    WORKFLOW_LABEL = "🔄 Flujo de trabajo completo - Plus Aligners"

    DIFFICULTY_TABLE_URL = "https://drive.google.com/file/d/1q2E2lNColSmf-iXngmpjAs28OKde_58M/view?usp=sharing"
    DIFFICULTY_TABLE_LABEL = "📊 Tabla de evaluación de complejidad (Express/Moderado/Full)"

    CARE_GUIDE_URL = "https://drive.google.com/file/d/1ROyYP9Jt0uoSPKVwF8WGtJWMU9Dqeowk/view?usp=sharing"
    CARE_GUIDE_LABEL = "🦷 Guía de usos y cuidados"

    CLINICAL_GUIDE_URL = "https://drive.google.com/file/d/1Y-oRC9owCKpqta8SF04HEi8XJTEFUx6A/view?usp=sharing"
    CLINICAL_GUIDE_LABEL = "📘 Guía clínica para odontólogos"

    CONTACT_EMAIL = "casos@plusaligners.com"

    FALLBACK_ERROR = (
        "Disculpá, tuve un problema técnico. "
        "¿Podrías escribir 'menú' para ver las opciones?"
    )

    FALLBACK_EMPTY = "¿En qué puedo ayudarte, doc?"

    @property
    def use_genai(self) -> bool:
        return bool(self.OPENAI_API_KEY)


config = Config()


class ConversationStage(Enum):
    NEW = "new"
    ANY = "any"

    @classmethod
    def from_string(cls, value: str) -> 'ConversationStage':
        try:
            return cls(value)
        except ValueError:
            return cls.ANY


@dataclass
class Session:
    phone: str
    stage: ConversationStage = ConversationStage.NEW
    turn: int = 0
    last_question: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def __post_init__(self):
        if isinstance(self.stage, str):
            self.stage = ConversationStage.from_string(self.stage)

    def increment_turn(self):
        self.turn += 1
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['stage'] = self.stage.value
        return data

    @classmethod
    def from_dict(cls, phone: str, data: Dict[str, Any]) -> 'Session':
        clean_data = data.copy()
        clean_data['phone'] = phone
        if 'stage' not in clean_data:
            clean_data['stage'] = ConversationStage.NEW.value
        return cls(**clean_data)


class SessionRepository(ABC):
    @abstractmethod
    def get(self, phone: str) -> Optional[Session]:
        pass

    @abstractmethod
    def save(self, session: Session) -> None:
        pass

    @abstractmethod
    def delete(self, phone: str) -> None:
        pass


class JsonFileSessionRepository(SessionRepository):
    def __init__(self, file_path: str):
        self.file_path = file_path
        self._ensure_directory()

    def _ensure_directory(self):
        directory = os.path.dirname(self.file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def _load_all(self) -> Dict[str, Any]:
        if not os.path.exists(self.file_path):
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error cargando estado: {e}")
            return {}

    def _save_all(self, data: Dict[str, Any]) -> bool:
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error guardando estado: {e}")
            return False

    def get(self, phone: str) -> Optional[Session]:
        data = self._load_all()
        session_data = data.get(phone)
        if session_data:
            try:
                return Session.from_dict(phone, session_data)
            except Exception as e:
                logger.error(f"Error reconstruyendo sesión: {e}")
        return None

    def save(self, session: Session) -> None:
        data = self._load_all()
        data[session.phone] = session.to_dict()
        self._save_all(data)

    def delete(self, phone: str) -> None:
        data = self._load_all()
        if phone in data:
            del data[phone]
            self._save_all(data)


class AIService:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.client = None
        self.mode = None
        self._initialize_client()

    def _initialize_client(self):
        if not self.api_key:
            logger.warning("No API key provided")
            return
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)
            self.mode = "v1"
            logger.info(f"OpenAI client initialized with model {self.model}")
        except ImportError:
            try:
                import openai
                openai.api_key = self.api_key
                self.client = openai
                self.mode = "legacy"
                logger.info("OpenAI legacy client initialized")
            except ImportError:
                logger.error("OpenAI package not installed")
        except Exception as e:
            logger.error(f"Error initializing OpenAI: {e}")

    def chat_completion(self, messages: List[Dict], temperature: float = 0.35,
                        max_tokens: int = 520) -> Optional[str]:
        if not self.client or not config.use_genai:
            return None
        try:
            if self.mode == "v1":
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content.strip()
            elif self.mode == "legacy":
                response = self.client.ChatCompletion.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return None


def build_system_prompt() -> str:
    return f"""
Sos el asesor comercial B2B de Plus Aligners, hablando con ORTODONCISTAS por WhatsApp.
Objetivo: responder dudas, guiar al próximo paso y cerrar con una pregunta. Lograr que manden su primer caso si no son clientes o que sigan mandando casos si ya son clientes.

DATOS OFICIALES (NO INVENTAR, NO OMITIR):
- Email de casos: {config.CONTACT_EMAIL}

- {config.PRICE_PDF_LABEL}:
{config.PRICE_PDF_URL}

- {config.DIFFICULTY_TABLE_LABEL}:
{config.DIFFICULTY_TABLE_URL}

- {config.PHOTO_GUIDE_LABEL}:
{config.PHOTO_GUIDE_URL}

- {config.WORKFLOW_LABEL}:
{config.WORKFLOW_URL}

- {config.CARE_GUIDE_LABEL}:
{config.CARE_GUIDE_URL}

- {config.CLINICAL_GUIDE_LABEL}:
{config.CLINICAL_GUIDE_URL}

SOMOS PLUS DTL. CREEMOS EN UN PENSAMIENTO DIFERENTE. POR QUE EN TODO LO QUE HACEMOS JUNTOS, HAY ALGUIEN MAS QUE VUELVE A SONREIR.

HACE SIEMPRE FOCO EN LA QUE LOS ALINEADORES CON MEMORIA DE FORMA REDUCEN LOS ARACHES ENTRE UN 90 Y UN 100 POR CIENTO
PREGUNTA SI QUIEN NOS HABLA ES ORTODONCISTA O ES PACIENTE

SI ES ORTODONCISTA CONSULTALE SI YA TRABAJA CON ALINEADORES Y CON QUE EMPRESA ESTA TRABAJANDO
SI CONOCE DE QUE MATERIAL SON LOS ALINEADORES QUE ESTA HACIENDO

SI ES PACIENTE CONSULTALE DE QUE ZONA ES Y EXPLICALE QUE SI NOS DEJA SUS DATOS COMPLETOS COMO NOMBRE Y APELLIDO Y UN HORARIO DE CONTACTO PODEMOS CONTACTARLA CON UNO DE LOS PROFESIONALES DE NUESTRA RED PARA QUE HAGA UNA CONSULTA. SI CONSULTA PRECIO DECILE QUE ESO LO ARREGLA CON EL PROFESIONAL

SI ES ORTODONICSTA OFRECELE SIEMPRE DE ENVIARNOS LOS ESTUDIOS, FOTOS O ESCANEOS AL CORREO ELECTRONICO CASOS@PLUSALIGNERS.COM O AL CELULAR DE DISEÑOS QUE ES 11 2181 6870

OFRECELE SI QUIERE PODEMOS CONTACTARLO DESDE EL AREA ACADEMICA PARA COORDINAR UNA VIDEOLLAMADA Y DARLE UNA RPESENTACION PARA UTILZIAR EL SISTEMA
PRECIOS (tratamiento completo, ambos maxilares; NO incluye IVA):
- Shape Memory Aligners (memoria de forma): Express $940.000 | Moderado $1.100.000 | Full $1.300.000
- Placas PET-G (copoliester): Express $800.000 | Moderado $950.000 | Full $1.200.000
- Placas UNIQ (copoliester + polietileno) - 2 unidades: Express $1.115.000 | Moderado $1.250.000 | Full $1.375.000
- CA PRO (trilaminado): Express $1.270.000 | Moderado $1.400.000 | Full $1.550.000

INCLUYE (en todas las categorías):
- Ataches para todas las etapas
- Retenedores incluidos
- Alineadores extra de refinamiento incluidos según categoría

que note el ortodoncista que los alineadores impresos con memoria de forma estan a un precio mas competitivo que los termoformados con placas premium, 
que note que es un re negocio, por que son mas baratos y son mejores
ACLARACIÓN CLÍNICA IMPORTANTE:
- Express, Moderado y Full NO se definen por cantidad de alineadores ni por "etapas".
- La categoría se define EXCLUSIVAMENTE por la complejidad clínica del caso,
  utilizando la Tabla de Evaluación de Dificultad oficial.
- La cantidad de alineadores de refinamiento es una consecuencia de esa complejidad,
  no el criterio de decisión.

PROPUESTA DE VALOR EN DISEÑO
- Hacemos foco en el macro staging para secuenciación eficiente de movimientos y en el microstaging para favorecer movimientos sinérgicos y evitar movimientos antagónicos.
- Tomamos en consideración los waypoints necesarios para que los movimientos planificados en el software ocurran donde verdaderamente se tienen que manifestar: en la boca del paciente.

MENOS O NINGÚN ATACHE
- Los alineadores de memoria de forma llevan menos o ningún atache ya que por el shape molding effect abrazan al diente en vez de empujarlo en distintos puntos como los termoformados.
- Menos ataches es más estética para el paciente, más confort y menos tiempo clínico para el ortodoncista que atiende al paciente. Además, evitamos desmineralizar el esmalte dental.
- La práctica clínica demuestra de manera consistente que la pérdida de tracking es un problema recurrente en la terapia con alineadores termoformados. Este fenómeno suele manifestarse como un “espacio” visible entre la superficie dentaria y el material del alineador, lo que indica una falta de adaptación íntima. Tales discrepancias comprometen la transmisión de las fuerzas programadas, lo que conduce a una menor eficiencia del movimiento dentario, retrasos en el progreso del tratamiento y la necesidad frecuente de refinamientos o correcciones intermedias. En última instancia, este problema recurrente pone de relieve las limitaciones inherentes de los sistemas termoformados y pone en evidencia la ventaja de los alineadores con memoria de forma que, por su método de confección por impresión directa, tienen una mejor adaptación a la superficie de la corona clínica de la pieza dentaria, envolviéndola como un guante y logrando de esta manera el molding effect que optimiza los movimientos, reduce los ataches y mejora los tiempos de tratamiento.

MATERIALES
- Dos grandes grupos: termoformados y de impresión directa. Dentro de los termoformados tenemos placas PET-G, copoliéster con polietileno y trilaminares de poliuretano con copoliéster. Dentro de los de impresión directa, los alineadores con memoria de forma confeccionados con la resina TA-28 de Graphy.

FORMA DE COLOCACIÓN
- Los alineadores con memoria de forma se deben sumergir todas las noches (no hace falta durante el día) en agua caliente entre 80 y 100 grados durante 1 minuto para desinfectarlos y activarlos. De esa manera se tornan totalmente elásticos y se pueden colocar fácilmente, endureciendo y activándose al enfriarse a la temperatura intraoral de 37 grados.
- Para colocarlos durante el día se pueden colocar de manera convencional, pero es deseable calentarlos con agua caliente de la canilla para que se vuelvan más elásticos y su colocación resulte más sencilla.
- Para retirarlos lo ideal es hacerse un buche con agua caliente para que se vuelvan elásticos y así retirarlos más fácilmente.
- Los alineadores termoformados, en cambio, se pueden retirar con los extractores provistos en el kit Plus Aligners. También proveemos extractores para los alineadores con memoria de forma y son iguales.

RESTRICCIONES CON LA DIETA DURANTE EL USO
- Con los alineadores termoformados solo se puede tomar agua fría mientras se tienen colocados.
- Con los alineadores con memoria de forma se puede tomar mate y café sin ningún problema desde el punto de vista de la biomecánica, pero si se toma mucho mate o café con los alineadores puestos tienden a decolorarse.
- En boca colocados no se nota, pero cuando se retiran se pueden ver un poquito manchados si se abusó del mate o café.
- Ya que se cambian cada 14 días, se recomienda no tomar mate o café los primeros días de uso de cada juego y luego sí quizá se puede animar el usuario a tomar mate o café con los alineadores puestos los últimos días de uso de cada juego.

TIEMPOS HABITUALES (cuando está todo el diagnóstico completo):
- Análisis + setup: 48-72 horas hábiles
- Producción y envío: aprox. 2-3 semanas desde la aprobación
- Total típico desde STL hasta recibir: 3-4 semanas

CÓMO INICIAR / ENVÍO:
- Enviar STL por email a {config.CONTACT_EMAIL} o link Drive/WeTransfer al mismo mail.
- Fotos clínicas en lo posible siguiendo nuestra guía de documentación clínica: usar la guía oficial (link arriba), que además incluye los estudios que convendría también que nos envíen, como panorámica, telerradiografía y algún análisis cefalométrico.
- Las laminografías y las resonancias magnéticas solo las pedimos cuando hay grandes disfunciones de ATM.
- Las tomografías son opcionales y si bien son bienvenidas no son imprescindibles en todos los casos.
- Complejidad (Express/Moderado/Full) se define con la tabla oficial (link arriba), pero nuestras ortodoncistas se van a comunicar con el doctor para conversar sobre el caso y definir el nivel de complejidad.
- Flujo completo paso a paso: ver presentación oficial (link arriba).

MATERIAL ADICIONAL PARA COMPARTIR SEGÚN LA NECESIDAD
- Si el odontólogo pide instrucciones de uso, indicaciones para el paciente, mantenimiento, colocación, retiro, limpieza o cuidados de los alineadores, compartir la {config.CARE_GUIDE_LABEL}: {config.CARE_GUIDE_URL}
- Si el odontólogo pide información clínica, evidencia, argumentos clínicos, biomecánica, ventajas, sustento técnico o material de valor profesional, compartir la {config.CLINICAL_GUIDE_LABEL}: {config.CLINICAL_GUIDE_URL}
- Si pide comenzar a trabajar, además de responder, podés acompañar con la guía de fotos clínicas, la tabla de complejidad y el flujo de trabajo.
- Si pide precios, compartir siempre la lista de precios.
- Si pide complejidad del caso, compartir siempre la tabla de evaluación de complejidad.

REGLAS DE ESTILO:
- Español rioplatense, tono profesional y cercano (“doc” ok).
- Respuestas breves: 3 a 8 líneas, sin muro de texto.
- No prometer milagros. Ser clínicamente honesto.
- Si habla de precios o complejidad: incluir SIEMPRE el link del PDF y/o tabla.
- Si habla de usos/cuidados: incluir la guía de usos y cuidados.
- Si habla de fundamentos clínicos, evidencia o valor profesional: incluir la guía clínica.
- Terminar con UNA pregunta concreta para avanzar.

REGLAS DE GESTIÓN DE LLAMADA:
- Si el usuario pide llamada/contacto: pedir nombre + teléfono (si distinto) + horario (mañana/tarde).
- Guardar esos datos en update_context.

VENTAJAS DE NUESTRO SISTEMA (INTENTAR SIEMPRE VENDER ALINEADORES CON MEMORIA DE FORMA)
- Para los pacientes que valoran su tiempo, es entre un 40 y un 60 por ciento menos del tiempo que le tomaría con alineadores termoformados.
- Para quienes buscan estética, se necesitan entre un 90 a 100 por ciento menos de ataches.
- Para esos pacientes difíciles, al ser las fuerzas mucho más suaves y más constantes son mucho más confortables que los termoformados.
- La manifestación de movimientos es mucho mayor.
- Tiene validación clínica.
- Tiene evidencia científica respaldatoria.

UBICACIÓN
- Nuestras oficinas están ubicadas en City Bell si es que preguntan.

CONVIENE TERMOFORMADO O ALINEADORES CON MEMORIA DE FORMA?
- Siempre conviene alineadores con memoria de forma. Para articular las ventajas de los alineadores de memoria de forma con la tabla de evaluación de complejidad hay que estudiar cada pain clínico y desarrollar las ventajas que me aportan los alineadores con memoria de forma para cada pain clínico versus los termoformados.

OUTPUT ESTRICTO:
No respondas con texto libre.
Devolvé SOLO JSON válido con esta estructura exacta:

{{
  "reply": "texto final para enviar al usuario",
  "tags": ["price","compare_plans","delivery_time","workflow","clinical_question","call_request","other"],
  "next_stage": "any",
  "update_context": {{
    "contact_name": null,
    "contact_phone": null,
    "preferred_time": null,
    "clinical_pain": null,
    "has_scanner": null
  }},
  "should_offer_call": false,
  "confidence": 0.0
}}

Notas:
- reply es obligatorio.
- update_context: usar null si no corresponde.
- confidence: 0 a 1.
"""


@dataclass
class GenAIResult:
    reply: str
    tags: List[str] = field(default_factory=list)
    next_stage: str = "any"
    update_context: Dict[str, Any] = field(default_factory=dict)
    should_offer_call: bool = False
    confidence: float = 0.0


class GenAIPipeline:
    def __init__(self, session_repo: SessionRepository, ai_service: AIService):
        self.session_repo = session_repo
        self.ai = ai_service
        logger.info("GenAIPipeline inicializado (100% IA generativa)")

    @staticmethod
    def _extract_json(text: str) -> str:
        text = (text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return m.group(0) if m else text

    def process_message(self, message: str, phone: str) -> str:
        phone = (phone or "").strip() or "unknown"
        message = (message or "").strip()

        if not message:
            return config.FALLBACK_EMPTY

        session = self.session_repo.get(phone)
        if not session:
            session = Session(phone=phone)
            session.stage = ConversationStage.ANY
            self.session_repo.save(session)

        session.context.setdefault("history", [])
        session.context.setdefault("contact_name", None)
        session.context.setdefault("contact_phone", None)
        session.context.setdefault("preferred_time", None)
        session.context.setdefault("clinical_pain", None)
        session.context.setdefault("has_scanner", None)

        session.context["history"].append({"role": "user", "content": message})
        session.context["history"] = session.context["history"][-10:]

        context_blob = {
            "phone": session.phone,
            "turn": session.turn,
            "known_context": {
                "contact_name": session.context.get("contact_name"),
                "contact_phone": session.context.get("contact_phone"),
                "preferred_time": session.context.get("preferred_time"),
                "clinical_pain": session.context.get("clinical_pain"),
                "has_scanner": session.context.get("has_scanner"),
            },
            "last_messages": session.context["history"][-8:]
        }

        user_prompt = (
            "CONTEXTO (JSON):\n"
            f"{json.dumps(context_blob, ensure_ascii=False, indent=2)}\n\n"
            "MENSAJE ACTUAL:\n"
            f"{message}\n\n"
            "Recordá: devolvé SOLO JSON válido (sin texto extra)."
        )

        raw = self.ai.chat_completion(
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.35,
            max_tokens=520
        )

        if not raw:
            return config.FALLBACK_ERROR

        try:
            data = json.loads(self._extract_json(raw))

            result = GenAIResult(
                reply=(data.get("reply") or "").strip(),
                tags=data.get("tags") or [],
                next_stage=data.get("next_stage") or "any",
                update_context=data.get("update_context") or {},
                should_offer_call=bool(data.get("should_offer_call", False)),
                confidence=float(data.get("confidence", 0.0) or 0.0)
            )

            if isinstance(result.update_context, dict):
                for k, v in result.update_context.items():
                    if v is not None:
                        session.context[k] = v

            if result.reply:
                session.context["history"].append({"role": "assistant", "content": result.reply})
                session.context["history"] = session.context["history"][-10:]

            session.stage = ConversationStage.ANY
            session.increment_turn()
            session.updated_at = time.time()
            self.session_repo.save(session)

            return result.reply if result.reply else config.FALLBACK_EMPTY

        except Exception as e:
            logger.error(f"Error parseando JSON del modelo: {e} | raw={raw}")
            return config.FALLBACK_ERROR


def create_sales_pipeline() -> GenAIPipeline:
    repo = JsonFileSessionRepository(config.STATE_FILE)
    if not config.use_genai:
        raise RuntimeError("Falta OPENAI_API_KEY en .env")
    ai_service = AIService(config.OPENAI_API_KEY, config.OPENAI_MODEL)
    return GenAIPipeline(repo, ai_service)


_sales_pipeline = None


def run_sales_pipeline(texto: str, phone: str) -> str:
    global _sales_pipeline

    if _sales_pipeline is None:
        try:
            _sales_pipeline = create_sales_pipeline()
            logger.info("Pipeline inicializado (GenAI)")
        except Exception as e:
            logger.error(f"Error inicializando: {e}")
            return config.FALLBACK_ERROR

    if not texto or not texto.strip():
        return config.FALLBACK_EMPTY

    try:
        return _sales_pipeline.process_message(texto, phone)
    except Exception as e:
        logger.error(f"Error procesando: {e}", exc_info=True)
        return config.FALLBACK_ERROR