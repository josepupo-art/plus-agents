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
    PRICE_PDF_LABEL = "📄 Lista de precios Marzo 2026"

    PHOTO_GUIDE_URL = "https://drive.google.com/file/d/1oE6RpAqPuMAoMJjQYAxt-aLiF5OAVM58/view?usp=sharing"
    PHOTO_GUIDE_LABEL = "📸 Guía de fotos clínicas"

    WORKFLOW_URL = "https://drive.google.com/file/d/1FM_Ydxv9U4YSVktNNoiL7Xp0J0YoRTjr/view?usp=sharing"
    WORKFLOW_LABEL = "🔄 Flujo de trabajo"

    DIFFICULTY_TABLE_URL = "https://drive.google.com/file/d/1q2E2lNColSmf-iXngmpjAs28OKde_58M/view?usp=sharing"
    DIFFICULTY_TABLE_LABEL = "📊 Tabla de complejidad"

    CARE_GUIDE_URL = "https://drive.google.com/file/d/1ROyYP9Jt0uoSPKVwF8WGtJWMU9Dqeowk/view?usp=sharing"
    CARE_GUIDE_LABEL = "🦷 Guía de usos y cuidados"

    CLINICAL_GUIDE_URL = "https://drive.google.com/file/d/1Y-oRC9owCKpqta8SF04HEi8XJTEFUx6A/view?usp=sharing"
    CLINICAL_GUIDE_LABEL = "📘 Guía clínica"

    FIRST_VISIT_GUIDE_URL = os.getenv("FIRST_VISIT_GUIDE_URL", "").strip()
    FIRST_VISIT_GUIDE_LABEL = "🧭 Guía para la primera consulta"

    CONTACT_EMAIL = "casos@plusaligners.com"
    DESIGNS_PHONE = "11 2181 6870"

    FALLBACK_ERROR = (
        "Disculpá, tuve un problema técnico. "
        "¿Podrías escribir tu consulta de nuevo?"
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
    def from_string(cls, value: str) -> "ConversationStage":
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
        data["stage"] = self.stage.value
        return data

    @classmethod
    def from_dict(cls, phone: str, data: Dict[str, Any]) -> "Session":
        clean_data = data.copy()
        clean_data["phone"] = phone
        if "stage" not in clean_data:
            clean_data["stage"] = ConversationStage.NEW.value
        return cls(**clean_data)


class SessionRepository(ABC):
    @abstractmethod
    def get(self, phone: str) -> Optional[Session]:
        raise NotImplementedError

    @abstractmethod
    def save(self, session: Session) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, phone: str) -> None:
        raise NotImplementedError


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

    def chat_completion(self, messages: List[Dict], temperature: float = 0.25,
                        max_tokens: int = 420) -> Optional[str]:
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
            if self.mode == "legacy":
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
        return None


@dataclass
class GenAIResult:
    reply: str
    tags: List[str] = field(default_factory=list)
    next_stage: str = "any"
    update_context: Dict[str, Any] = field(default_factory=dict)
    should_offer_call: bool = False
    confidence: float = 0.0


ALLOWED_TAGS = {
    "price",
    "compare_plans",
    "delivery_time",
    "workflow",
    "clinical_question",
    "call_request",
    "other",
}


class Heuristics:
    @staticmethod
    def normalize(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().lower())

    @staticmethod
    def classify_lead_type(text: str, ctx: Dict[str, Any]) -> Optional[str]:
        t = Heuristics.normalize(text)
        if "ortodonc" in t or "ortopedia" in t or "doc" in t:
            return "orthodontist"
        if "paciente" in t:
            return "patient"
        return ctx.get("lead_type")

    @staticmethod
    def infer_experience_level(text: str, ctx: Dict[str, Any]) -> Optional[str]:
        t = Heuristics.normalize(text)
        if any(x in t for x in ["muy poco", "recién empiezo", "quiero empezar", "todavía no", "no, quiero empezar", "casi nada"]):
            return "beginner"
        if any(x in t for x in ["si trabajo", "sí trabajo", "trabajo con", "invisalign", "line up", "lineup", "no bracks", "in office"]):
            return "experienced"
        return ctx.get("experience_level")

    @staticmethod
    def infer_stage(text: str, ctx: Dict[str, Any]) -> Optional[str]:
        t = Heuristics.normalize(text)
        if any(x in t for x in ["no tengo un caso", "primera consulta", "presupuesto", "presupuestos", "posibles presupuestos"]):
            return "pre_case_budgeting"
        if any(x in t for x in ["quiero mandar un caso", "quiero ver de hacer un caso", "cuando tenga un caso", "en cualquier momento me entra uno", "veamos un caso", "enviar un caso"]):
            return "ready_for_case"
        if any(x in t for x in ["averiguar detalles", "son alineadores estampados o impresos", "como trabajan", "cómo trabajan"]):
            return "comparative_evaluation"
        return ctx.get("commercial_stage")

    @staticmethod
    def infer_current_system(text: str, ctx: Dict[str, Any]) -> Optional[str]:
        t = Heuristics.normalize(text)
        mapping = [
            ("invisalign", "Invisalign"),
            ("line up", "Line Up"),
            ("lineup", "Line Up"),
            ("no bracks", "No Bracks"),
            ("in office", "In office"),
            ("graphy", "Graphy"),
        ]
        for key, value in mapping:
            if key in t:
                return value
        return ctx.get("current_system")

    @staticmethod
    def infer_intent(text: str) -> Optional[str]:
        t = Heuristics.normalize(text)
        if re.search(r"\bprecio|precios|costos|costo\b", t):
            return "price"
        if any(x in t for x in ["tiempo", "demora", "entrega"]):
            return "delivery_time"
        if any(x in t for x in ["flujo", "workflow", "como trabajan", "cómo trabajan", "etapas"]):
            return "workflow"
        if any(x in t for x in ["guia clínica", "guía clínica", "evidencia", "biomec", "molding", "shape memory", "impresos", "impresión directa", "graphy"]):
            return "clinical_question"
        if any(x in t for x in ["llamen", "llamada", "videollamada", "presentación", "presentacion"]):
            return "call_request"
        return None

    @staticmethod
    def detect_nonexistent_asset_request(text: str) -> bool:
        t = Heuristics.normalize(text)
        return (
            "presentación para pacientes" in t
            or "presentacion para pacientes" in t
            or "mostrarle a los pacientes" in t
        )


class PromptFactory:
    @staticmethod
    def build_system_prompt() -> str:
        first_visit_line = (
            f"- {config.FIRST_VISIT_GUIDE_LABEL}: {config.FIRST_VISIT_GUIDE_URL}\n"
            if config.FIRST_VISIT_GUIDE_URL else ""
        )

        return f"""
Sos el asesor comercial B2B de Plus Aligners por WhatsApp.

OBJETIVO REAL
- No vender "de una".
- Tu objetivo es mover al colega al siguiente paso correcto según su etapa mental.
- Cada mensaje debe buscar UNA sola microconversión.
- No abrir varias opciones a la vez.

TIPOS DE LEAD ORTODONCISTA
1. beginner: quiere empezar con alineadores.
2. pre_case_budgeting: todavía no tiene caso, pero quiere saber cómo presupuestar y ofrecerlo en primera consulta.
3. ready_for_case: quiere mandar un caso o está por entrarle uno.
4. comparative_evaluation: ya usa otro sistema y quiere comparar detalles de Plus.

REGLAS CLAVE
- No prometas assets ni acciones que no existan.
- No digas que vas a enviar algo si no tenés el link o no podés ejecutarlo.
- No ofrezcas "presentación para pacientes" salvo que exista realmente un link configurado.
- Si te piden algo que no existe, decilo con honestidad y ofrecé la alternativa más cercana.
- No repitas en todos los mensajes "90% a 100% menos ataches". Si ya lo dijiste, variá o avanzá.
- No uses siempre el mismo cierre: "¿querés que veamos un caso?"
- Si el lead está en pre_case_budgeting, NO empujes enseguida a mandar STL.
- Si el lead está en ready_for_case, reducí fricción y dale el canal más simple.
- Si el lead ya usa otro sistema y dice que le funciona bien, no vendas desde el dolor: vendé desde la diferencia.

GRAPHY
- Graphy es proveedor tecnológico e insumo de Plus Aligners.
- No lo trates como competidor.
- Si el usuario menciona Graphy, podés decir que Plus Aligners trabaja con resina y tecnología Graphy, y que Plus aporta diseño, staging, producción y acompañamiento clínico.

VENTAJAS PRINCIPALES DE LOS ALINEADORES CON MEMORIA DE FORMA DE PLUS ALIGNERS
- Frente a los alineadores termoformados, estas son las ventajas principales que debés poder usar en la conversación cuando correspondan.
- No las metas todas juntas salvo que el usuario pida una comparación amplia.
- Elegí la ventaja según el perfil, el pain o la intención del colega.
- No suenes exagerado ni como folleto.

1. TIEMPO DE TRATAMIENTO
- Para pacientes que valoran su tiempo, los tratamientos con alineadores con memoria de forma de Plus Aligners pueden tardar entre un 40% y un 60% menos que con alineadores termoformados.
- Usá esta ventaja cuando aparezcan temas como duración del tratamiento, eficiencia, tiempos clínicos o interés por acelerar resultados.

2. ESTÉTICA Y MENOR NECESIDAD DE ATACHES
- Para quienes buscan estética y también proteger el esmalte dental del ataque del ácido fosfórico, los alineadores con memoria de forma requieren entre un 90% y un 100% menos de ataches que los termoformados.
- Usá esta ventaja cuando aparezcan temas como estética, ataches, grabado ácido, comodidad visual del paciente o simplificación clínica.

3. CONFORT
- Para quienes buscan confort, los alineadores con memoria de forma son más cómodos y más suaves que los termoformados.
- Usá esta ventaja cuando aparezcan temas como dolor, adaptación del paciente, sensibilidad o experiencia de uso.

4. CUIDADO DEL DIENTE Y DE SUS ESTRUCTURAS DE SOPORTE
- Para pacientes con riesgo de recesiones gingivales o reabsorciones radiculares, las fuerzas más suaves y gentiles de esta tecnología más sofisticada cuidan mejor tanto al diente como a sus estructuras de soporte.
- Usá esta ventaja cuando aparezcan temas periodontales, biología, seguridad del movimiento, fuerzas, recesión gingival, reabsorción radicular o pacientes delicados.

REGLA DE USO DE ESTAS VENTAJAS
- Si el colega pregunta por diferencias, podés comparar contra termoformados.
- Si el colega ya trabaja con alineadores, elegí la ventaja más relevante según su contexto.
- Si el lead no expresa dolor, no inventes uno: mostrá la diferencia de Plus de forma elegante.
- Si ya hablaste de menos ataches, en el siguiente mensaje priorizá otra ventaja si el contexto lo permite.

ACTIVOS REALES DISPONIBLES
- {config.PRICE_PDF_LABEL}: {config.PRICE_PDF_URL}
- {config.PHOTO_GUIDE_LABEL}: {config.PHOTO_GUIDE_URL}
- {config.WORKFLOW_LABEL}: {config.WORKFLOW_URL}
- {config.DIFFICULTY_TABLE_LABEL}: {config.DIFFICULTY_TABLE_URL}
- {config.CARE_GUIDE_LABEL}: {config.CARE_GUIDE_URL}
- {config.CLINICAL_GUIDE_LABEL}: {config.CLINICAL_GUIDE_URL}
{first_visit_line}- Email de casos: {config.CONTACT_EMAIL}
- WhatsApp del área de diseños: {config.DESIGNS_PHONE}

REGLAS DE USO DE ASSETS
- beginner: priorizá precios + tiempos + guía simple. No mandes tres links juntos.
- pre_case_budgeting: explicá que el presupuesto se orienta por complejidad, no por cantidad exacta de placas. Si existe la guía de primera consulta, es el asset ideal.
- ready_for_case: priorizá guía de fotos + mail + WhatsApp de diseños.
- comparative_evaluation: priorizá explicación breve + guía clínica + precios si los pide.
- La guía de cuidados NO sirve para conversión inicial; solo para uso e indicaciones.

REGLA DE PRESUPUESTO
- Plus Aligners no define Express/Moderado/Full por cantidad de alineadores.
- Se define por complejidad clínica según la tabla oficial.
- Si preguntan cómo presupuestar en primera consulta sin STL, respondé esto con claridad: en la primera consulta se orienta por complejidad probable, no por número exacto de placas.
- No digas que un caso severo se define por x cantidad de alineadores.

TONO
- Español rioplatense.
- Profesional, cercano, corto.
- Máximo ideal: 2 a 5 líneas.
- Terminá con UNA pregunta concreta solo si realmente ayuda a avanzar.
- Si ya cerraste bien el paso, también podés cerrar sin preguntar.

CUÁNDO OFRECER LLAMADA
- Solo ofrecer llamada/videollamada si:
  a) la pide el usuario,
  b) está muy técnico y lo amerita,
  c) hay una objeción compleja que no conviene estirar por chat.

PRECIOS OFICIALES RELEVANTES
- Shape Memory x2: Express $940.000 | Moderado $1.100.000 | Full $1.300.000
- PET-G x2: Express $800.000 | Moderado $950.000 | Full $1.200.000
- UNIQ x2: Express $1.115.000 | Moderado $1.250.000 | Full $1.375.000
- CA PRO x2: Express $1.270.000 | Moderado $1.400.000 | Full $1.550.000
- No incluye IVA.
- Incluye ataches, retenedores y refinamientos según categoría.

RESPUESTAS DE REFERENCIA
- Si el colega dice que recién empieza, ayudalo a arrancar simple.
- Si dice que no tiene caso todavía, ayudalo a presupuestar y ofrecerlo.
- Si dice que ya usa un sistema que le funciona, no discutas; explicá la diferencia de Plus.
- Si dice "en cualquier momento me entra uno", dejalo listo para actuar rápido.
- Si pide algo que no existe, no inventes.

SALIDA
Devolvé SOLO JSON válido con esta estructura:
{{
  "reply": "texto final",
  "tags": ["price","compare_plans","delivery_time","workflow","clinical_question","call_request","other"],
  "next_stage": "any",
  "update_context": {{
    "lead_type": null,
    "experience_level": null,
    "commercial_stage": null,
    "current_system": null,
    "contact_name": null,
    "contact_phone": null,
    "preferred_time": null,
    "clinical_pain": null,
    "has_scanner": null,
    "last_cta": null,
    "last_asset_sent": null
  }},
  "should_offer_call": false,
  "confidence": 0.0
}}
""".strip()


class ResponseGuards:
    @staticmethod
    def sanitize_reply(reply: str) -> str:
        text = (reply or "").strip()
        text = text.replace("[enlace a la presentación]", "")
        text = text.replace("[link]", "")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def ensure_no_fake_promise(reply: str) -> str:
        forbidden = [
            "te envío la presentación",
            "te la envío por whatsapp ahora mismo",
            "te la mando por aquí",
        ]
        normalized = Heuristics.normalize(reply)
        if any(x in normalized for x in forbidden):
            return (
                "Puedo orientarte por acá y compartirte el material que sí tenemos disponible. "
                "Decime qué necesitás ver primero: precios, complejidad, flujo de trabajo o guía clínica."
            )
        return reply

    @staticmethod
    def cap_links(reply: str) -> str:
        urls = re.findall(r"https?://\S+", reply)
        if len(urls) <= 2:
            return reply
        keep = set(urls[:2])
        parts = reply.split()
        rebuilt = []
        for part in parts:
            if re.match(r"https?://\S+", part) and part not in keep:
                continue
            rebuilt.append(part)
        return " ".join(rebuilt)


class GenAIPipeline:
    def __init__(self, session_repo: SessionRepository, ai_service: AIService):
        self.session_repo = session_repo
        self.ai = ai_service
        logger.info("GenAIPipeline inicializado (v2 híbrido)")

    @staticmethod
    def _extract_json(text: str) -> str:
        text = (text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return m.group(0) if m else text

    @staticmethod
    def _new_session(phone: str) -> Session:
        session = Session(phone=phone)
        session.stage = ConversationStage.ANY
        session.context = {
            "history": [],
            "lead_type": None,
            "experience_level": None,
            "commercial_stage": None,
            "current_system": None,
            "contact_name": None,
            "contact_phone": None,
            "preferred_time": None,
            "clinical_pain": None,
            "has_scanner": None,
            "last_cta": None,
            "last_asset_sent": None,
        }
        return session

    @staticmethod
    def _apply_heuristics(session: Session, message: str):
        ctx = session.context
        lead_type = Heuristics.classify_lead_type(message, ctx)
        experience_level = Heuristics.infer_experience_level(message, ctx)
        commercial_stage = Heuristics.infer_stage(message, ctx)
        current_system = Heuristics.infer_current_system(message, ctx)
        detected_intent = Heuristics.infer_intent(message)

        if lead_type:
            ctx["lead_type"] = lead_type
        if experience_level:
            ctx["experience_level"] = experience_level
        if commercial_stage:
            ctx["commercial_stage"] = commercial_stage
        if current_system:
            ctx["current_system"] = current_system
        if detected_intent:
            ctx["detected_intent"] = detected_intent

    def _hardcoded_reply(self, session: Session, message: str) -> Optional[GenAIResult]:
        t = Heuristics.normalize(message)
        ctx = session.context

        if Heuristics.detect_nonexistent_asset_request(t):
            reply = (
                "Hoy no tenemos una presentación específica para pacientes lista para enviar. "
                "Lo que sí puedo compartirte es material real para que orientes la primera consulta y expliques el sistema con claridad. "
            )
            if config.FIRST_VISIT_GUIDE_URL:
                reply += f"Te dejo {config.FIRST_VISIT_GUIDE_LABEL}: {config.FIRST_VISIT_GUIDE_URL}"
                ctx["last_asset_sent"] = "first_visit_guide"
                ctx["last_cta"] = "shared_first_visit_guide"
            else:
                reply += (
                    f"Si querés, te paso {config.PRICE_PDF_LABEL.lower()} o la {config.CLINICAL_GUIDE_LABEL.lower()}."
                )
                ctx["last_cta"] = "offered_real_assets"
            return GenAIResult(reply=reply, tags=["other"], confidence=0.99)

        if ctx.get("lead_type") == "patient" and re.search(r"\bprecio|precios|costo|costos\b", t):
            reply = (
                f"El valor final lo define el profesional tratante. Si querés, te vinculamos con un profesional de la red. "
                "Pasame por favor tu nombre y apellido, tu zona y un horario de contacto."
            )
            ctx["last_cta"] = "asked_patient_data"
            return GenAIResult(reply=reply, tags=["price", "other"], confidence=0.99)

        if ctx.get("lead_type") == "orthodontist" and ctx.get("commercial_stage") == "pre_case_budgeting":
            if re.search(r"\bprecio|precios|presupuesto|presupuestar|costos|costo\b", t):
                reply = (
                    f"En la primera consulta lo más práctico es orientar el presupuesto por complejidad probable, no por cantidad exacta de placas. "
                    f"En Plus Aligners la categoría Express / Moderado / Full se define por complejidad clínica y no por número de alineadores. "
                    f"Te paso la lista oficial: {config.PRICE_PDF_URL}"
                )
                if config.FIRST_VISIT_GUIDE_URL:
                    reply += f"\n\nY si te sirve para consulta inicial, te dejo también {config.FIRST_VISIT_GUIDE_LABEL}: {config.FIRST_VISIT_GUIDE_URL}"
                    ctx["last_asset_sent"] = "first_visit_guide"
                ctx["last_cta"] = "shared_budgeting_guidance"
                return GenAIResult(reply=reply, tags=["price", "other"], confidence=0.99)

        if ctx.get("lead_type") == "orthodontist" and ctx.get("commercial_stage") == "ready_for_case":
            if re.search(r"\bsi\b|dale|oki|ok|perfecto", t) and ctx.get("last_cta") in {"offered_case_channel", "offered_photo_guide"}:
                reply = (
                    f"Perfecto doc. Te dejo la {config.PHOTO_GUIDE_LABEL.lower()}: {config.PHOTO_GUIDE_URL}\n\n"
                    f"Cuando quieras, podés enviarlo a {config.CONTACT_EMAIL} o al WhatsApp de diseños {config.DESIGNS_PHONE}."
                )
                ctx["last_asset_sent"] = "photo_guide"
                ctx["last_cta"] = "shared_photo_guide"
                return GenAIResult(reply=reply, tags=["workflow"], confidence=0.98)

        if ctx.get("lead_type") == "orthodontist" and ctx.get("commercial_stage") == "comparative_evaluation":
            if "graphy" in t:
                reply = (
                    "Trabajamos con alineadores de impresión directa usando resina y tecnología Graphy. "
                    "Graphy es nuestro proveedor tecnológico; desde Plus aportamos diseño, staging, producción y acompañamiento clínico."
                )
                ctx["last_cta"] = "explained_graphy_relationship"
                return GenAIResult(reply=reply, tags=["clinical_question", "compare_plans"], confidence=0.99)

        return None

    def process_message(self, message: str, phone: str) -> str:
        phone = (phone or "").strip() or "unknown"
        message = (message or "").strip()

        if not message:
            return config.FALLBACK_EMPTY

        session = self.session_repo.get(phone)
        if not session:
            session = self._new_session(phone)

        session.context.setdefault("history", [])
        session.context["history"].append({"role": "user", "content": message})
        session.context["history"] = session.context["history"][-12:]

        self._apply_heuristics(session, message)

        hardcoded = self._hardcoded_reply(session, message)
        if hardcoded and hardcoded.reply:
            session.context["history"].append({"role": "assistant", "content": hardcoded.reply})
            session.context["history"] = session.context["history"][-12:]
            session.increment_turn()
            self.session_repo.save(session)
            return hardcoded.reply

        context_blob = {
            "phone": session.phone,
            "turn": session.turn,
            "known_context": {
                "lead_type": session.context.get("lead_type"),
                "experience_level": session.context.get("experience_level"),
                "commercial_stage": session.context.get("commercial_stage"),
                "current_system": session.context.get("current_system"),
                "contact_name": session.context.get("contact_name"),
                "contact_phone": session.context.get("contact_phone"),
                "preferred_time": session.context.get("preferred_time"),
                "clinical_pain": session.context.get("clinical_pain"),
                "has_scanner": session.context.get("has_scanner"),
                "last_cta": session.context.get("last_cta"),
                "last_asset_sent": session.context.get("last_asset_sent"),
                "detected_intent": session.context.get("detected_intent"),
            },
            "last_messages": session.context["history"][-8:],
        }

        user_prompt = (
            "CONTEXTO (JSON):\n"
            f"{json.dumps(context_blob, ensure_ascii=False, indent=2)}\n\n"
            "MENSAJE ACTUAL:\n"
            f"{message}\n\n"
            "Recordá: una sola microconversión, sin inventar assets ni promesas operativas."
        )

        raw = self.ai.chat_completion(
            messages=[
                {"role": "system", "content": PromptFactory.build_system_prompt()},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.25,
            max_tokens=420,
        )

        if not raw:
            return config.FALLBACK_ERROR

        try:
            data = json.loads(self._extract_json(raw))
            result = GenAIResult(
                reply=(data.get("reply") or "").strip(),
                tags=[t for t in (data.get("tags") or []) if t in ALLOWED_TAGS],
                next_stage=(data.get("next_stage") or "any").strip() or "any",
                update_context=data.get("update_context") or {},
                should_offer_call=bool(data.get("should_offer_call", False)),
                confidence=float(data.get("confidence", 0.0) or 0.0),
            )

            result.reply = ResponseGuards.sanitize_reply(result.reply)
            result.reply = ResponseGuards.ensure_no_fake_promise(result.reply)
            result.reply = ResponseGuards.cap_links(result.reply)

            if not result.reply:
                return config.FALLBACK_EMPTY

            if isinstance(result.update_context, dict):
                for k, v in result.update_context.items():
                    if v is not None:
                        session.context[k] = v

            if result.tags:
                if "price" in result.tags:
                    session.context["last_cta"] = "shared_prices"
                    session.context["last_asset_sent"] = "price_list"
                elif "workflow" in result.tags:
                    session.context["last_cta"] = "shared_workflow"
                elif "clinical_question" in result.tags:
                    session.context["last_cta"] = "answered_clinical_question"

            session.context["history"].append({"role": "assistant", "content": result.reply})
            session.context["history"] = session.context["history"][-12:]
            session.increment_turn()
            session.updated_at = time.time()
            self.session_repo.save(session)
            return result.reply

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
            logger.info("Pipeline inicializado (GenAI v2)")
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
