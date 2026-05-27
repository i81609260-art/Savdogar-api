"""ML-based chat service — TF-IDF + cosine similarity + intent classification."""

import re
from dataclasses import dataclass
from typing import Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity


# ---------------------------------------------------------------------------
# Training data for intent classifier
# ---------------------------------------------------------------------------
INTENT_TRAINING = [
    # price
    ("narx qancha", "price"),
    ("qancha turadi", "price"),
    ("pul qancha", "price"),
    ("cost qancha", "price"),
    ("arzon turmi", "price"),
    ("narxi", "price"),
    ("dollar", "price"),
    ("som", "price"),
    ("to'lov", "price"),
    ("цена", "price"),
    ("сколько стоит", "price"),
    # availability
    ("joy bormi", "availability"),
    ("bo'sh joylar", "availability"),
    ("mavjudmi", "availability"),
    ("qachon boshlanadi", "availability"),
    ("sana", "availability"),
    ("qachon", "availability"),
    ("bor turmi", "availability"),
    ("есть ли места", "availability"),
    ("свободно", "availability"),
    # booking
    ("bron qilmoqchi", "booking"),
    ("bron qilish", "booking"),
    ("ro'yxatdan o'tmoqchi", "booking"),
    ("buyurtma bermoqchi", "booking"),
    ("olmoqchi", "booking"),
    ("sotib olmoqchi", "booking"),
    ("забронировать", "booking"),
    ("заказать", "booking"),
    # tours_list
    ("turlar", "tours_list"),
    ("qanday turlar bor", "tours_list"),
    ("destinatsiya", "tours_list"),
    ("qayerlarga", "tours_list"),
    ("yo'nalishlar", "tours_list"),
    ("paketlar", "tours_list"),
    ("туры", "tours_list"),
    ("направления", "tours_list"),
    # duration
    ("necha kun", "duration"),
    ("qancha davom", "duration"),
    ("muddat", "duration"),
    ("дней", "duration"),
    ("сколько дней", "duration"),
    # contact
    ("telefon", "contact"),
    ("bog'lanish", "contact"),
    ("aloqa", "contact"),
    ("manzil", "contact"),
    ("kontakt", "contact"),
    ("связаться", "contact"),
    ("телефон", "contact"),
    # greeting
    ("salom", "greeting"),
    ("assalomu alaykum", "greeting"),
    ("xayr", "greeting"),
    ("rahmat", "greeting"),
    ("привет", "greeting"),
    ("здравствуйте", "greeting"),
]


@dataclass
class Tour:
    id: int
    title: str
    description: str
    city: str
    country: str
    price: float
    duration_days: int
    start_date: str
    available_slots: int


@dataclass
class Company:
    name: str
    description: str
    city: str
    phone: str
    email: str


class MLChatService:
    """Per-company ML chat engine. Indexes company tours on first use."""

    def __init__(self):
        self._intent_model = LogisticRegression(max_iter=1000)
        self._intent_vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(2, 4), min_df=1
        )
        self._tour_vectorizers: dict[int, TfidfVectorizer] = {}
        self._tour_matrices: dict[int, np.ndarray] = {}
        self._tour_data: dict[int, list[Tour]] = {}
        self._trained = False
        self._train_intent_model()

    def _train_intent_model(self):
        texts = [t for t, _ in INTENT_TRAINING]
        labels = [l for _, l in INTENT_TRAINING]
        X = self._intent_vectorizer.fit_transform(texts)
        self._intent_model.fit(X, labels)
        self._trained = True

    def _detect_intent(self, text: str) -> str:
        X = self._intent_vectorizer.transform([text.lower()])
        return self._intent_model.predict(X)[0]

    def index_company_tours(self, company_id: int, tours: list[Tour]):
        """Build TF-IDF index for a company's tours."""
        if not tours:
            self._tour_data[company_id] = []
            return

        corpus = []
        for t in tours:
            doc = (
                f"{t.title} {t.city} {t.country} "
                f"{t.description or ''} "
                f"{t.duration_days} kun "
                f"narx {t.price}"
            )
            corpus.append(doc.lower())

        vec = TfidfVectorizer(analyzer="word", ngram_range=(1, 2))
        matrix = vec.fit_transform(corpus)
        self._tour_vectorizers[company_id] = vec
        self._tour_matrices[company_id] = matrix
        self._tour_data[company_id] = tours

    def _find_relevant_tours(self, company_id: int, query: str, top_k: int = 3) -> list[Tour]:
        if company_id not in self._tour_vectorizers:
            return []
        vec = self._tour_vectorizers[company_id]
        matrix = self._tour_matrices[company_id]
        q_vec = vec.transform([query.lower()])
        scores = cosine_similarity(q_vec, matrix).flatten()
        top_indices = scores.argsort()[::-1][:top_k]
        tours = self._tour_data[company_id]
        return [tours[i] for i in top_indices if scores[i] > 0.01]

    def respond(
        self,
        company_id: int,
        company: Company,
        user_message: str,
        history: Optional[list[dict]] = None,
    ) -> str:
        intent = self._detect_intent(user_message)
        relevant = self._find_relevant_tours(company_id, user_message)
        all_tours = self._tour_data.get(company_id, [])

        if intent == "greeting":
            return (
                f"Salom! Men {company.name} kompaniyasining virtual assistentiman. "
                f"Turlar, narxlar va bron haqida savol bering — yordam beraman! 😊"
            )

        if intent == "contact":
            return (
                f"📞 **{company.name}** bilan bog'lanish:\n"
                f"- Telefon: {company.phone}\n"
                f"- Email: {company.email}\n"
                f"- Shahar: {company.city}"
            )

        if intent == "tours_list":
            if not all_tours:
                return f"{company.name} kompaniyasida hozircha tur paketlar mavjud emas."
            lines = [f"✈️ **{company.name}** tur yo'nalishlari:\n"]
            for t in all_tours[:6]:
                lines.append(f"• **{t.title}** — {t.city}, {t.country} | {t.duration_days} kun | ${t.price:,.0f}")
            if len(all_tours) > 6:
                lines.append(f"\n...va yana {len(all_tours) - 6} ta tur mavjud.")
            return "\n".join(lines)

        if intent == "price":
            tours = relevant or all_tours[:3]
            if not tours:
                return "Hozirda narx ma'lumoti mavjud emas."
            lines = ["💰 **Narxlar:**\n"]
            for t in tours:
                lines.append(f"• **{t.title}**: ${t.price:,.0f} (1 kishi uchun)")
            return "\n".join(lines)

        if intent == "availability":
            tours = relevant or all_tours[:3]
            if not tours:
                return "Hozirda mavjud turlar yo'q."
            lines = ["📅 **Mavjud turlar:**\n"]
            for t in tours:
                slot_text = f"{t.available_slots} joy" if t.available_slots > 0 else "❌ Joy yo'q"
                lines.append(
                    f"• **{t.title}** — {t.start_date} | {slot_text}"
                )
            return "\n".join(lines)

        if intent == "duration":
            tours = relevant or all_tours[:3]
            if not tours:
                return "Davomiylik ma'lumoti mavjud emas."
            lines = ["⏱️ **Tur davomiyligi:**\n"]
            for t in tours:
                lines.append(f"• **{t.title}**: {t.duration_days} kun ({t.city}, {t.country})")
            return "\n".join(lines)

        if intent == "booking":
            tours = relevant or all_tours[:1]
            if not tours:
                return (
                    f"Bron qilish uchun {company.phone} raqamiga murojaat qiling "
                    f"yoki saytdagi bron tugmasini bosing."
                )
            t = tours[0]
            return (
                f"✅ **{t.title}** turini bron qilish uchun:\n"
                f"1. Tur kartasidagi **'Bron qilish'** tugmasini bosing\n"
                f"2. Yoki {company.phone} raqamiga qo'ng'iroq qiling\n\n"
                f"Narx: ${t.price:,.0f} | Joy: {t.available_slots} ta mavjud"
            )

        # Fallback — semantic search
        if relevant:
            t = relevant[0]
            return (
                f"**{t.title}** bo'yicha ma'lumot:\n"
                f"📍 {t.city}, {t.country}\n"
                f"⏱️ {t.duration_days} kun\n"
                f"💰 ${t.price:,.0f}\n"
                f"📅 Boshlanish: {t.start_date}\n"
                f"🪑 Bo'sh joy: {t.available_slots} ta"
            )

        return (
            f"Savolingizni tushunmadim. "
            f"{company.name} bo'yicha narx, joy mavjudligi, "
            f"bron yoki yo'nalishlar haqida so'rang. "
            f"Yordam kerak bo'lsa: {company.phone}"
        )


# Singleton — bir marta yaratiladi, barcha requestlar ishlatadi
ml_chat = MLChatService()
