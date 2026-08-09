"""Psixologik anketa: odamning sayohat profilini aniqlaydi.

Nega "qayerga bormoqchisiz?" deb so'ramaymiz — mijozning aksariyati buni
o'zi ham bilmaydi. "Antalya" deb javob bergan odam aslida tinchlik
qidirayotgan bo'lishi mumkin va Antalyaning shovqinli mehmonxonasidan
norozi qaytadi. Shuning uchun savollar SAYOHAT haqida emas, ODAM haqida:
javoblardan to'rtta o'lcham chiqadi va tur toifasi shundan tanlanadi.

Bu yerda LLM yo'q va kerak ham emas: savollar oldindan ma'lum, javoblar
yopiq ro'yxat, ballar esa oddiy qo'shish. Tashqi API'ga bog'lanish bu
qadamni sekin va ishonchsiz qilardi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.services.tour_taxonomy import Board, TourCategory

# O'lchamlar. Har biri 0..1 oralig'ida; 0.5 — betaraf.
#
# Ular QARAMA-QARSHI juftlik: bittasi past bo'lsa qarama-qarshi xohish
# kuchli degani. Shu sababli alohida "faollik" o'lchami yo'q — u
# `sokinlik`ning teskarisi.
Dimension = Literal["sokinlik", "yangilik", "davra", "tartib"]

DIMENSIONS: tuple[Dimension, ...] = ("sokinlik", "yangilik", "davra", "tartib")

DIMENSION_LABELS: dict[Dimension, dict[str, str]] = {
    "sokinlik": {
        "uz": "Tinchlik ↔ Harakat",
        "ru": "Спокойствие ↔ Активность",
        "en": "Calm ↔ Activity",
    },
    "yangilik": {
        "uz": "Tanish ↔ Yangilik",
        "ru": "Привычное ↔ Новое",
        "en": "Familiar ↔ Novelty",
    },
    "davra": {
        "uz": "Yolg'izlik ↔ Davra",
        "ru": "Уединение ↔ Компания",
        "en": "Solitude ↔ Crowd",
    },
    "tartib": {
        "uz": "Erkinlik ↔ Reja",
        "ru": "Свобода ↔ План",
        "en": "Spontaneity ↔ Plan",
    },
}


@dataclass(frozen=True)
class Answer:
    """Bitta javob va uning o'lchamlarga ta'siri.

    `weights` -1..+1 oralig'ida. Nol yozilmaydi — ta'sir qilmaydigan
    o'lcham umuman ko'rsatilmaydi, shunda javobning MA'NOSI ko'rinib
    turadi.
    """

    id: str
    text: dict[str, str]
    weights: dict[Dimension, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Question:
    id: str
    text: dict[str, str]
    answers: tuple[Answer, ...]


QUESTIONS: tuple[Question, ...] = (
    Question(
        id="hafta_oxiri",
        text={
            "uz": "Og'ir hafta tugadi. Dam olish kuni nima qilasiz?",
            "ru": "Тяжёлая неделя позади. Что делаете в выходной?",
            "en": "A hard week is over. What do you do on your day off?",
        },
        answers=(
            Answer("uy", {
                "uz": "Uyda qolaman, hech kim bezovta qilmasin",
                "ru": "Останусь дома, чтобы никто не беспокоил",
                "en": "Stay home, undisturbed",
            }, {"sokinlik": 0.9, "davra": -0.7}),
            Answer("dostlar", {
                "uz": "Do'stlar bilan uchrashaman",
                "ru": "Встречусь с друзьями",
                "en": "Meet up with friends",
            }, {"davra": 0.9, "sokinlik": -0.3}),
            Answer("yangi_joy", {
                "uz": "Hali bormagan joyga boraman",
                "ru": "Поеду туда, где ещё не был",
                "en": "Go somewhere I have never been",
            }, {"yangilik": 0.9, "sokinlik": -0.5}),
            Answer("ishlar", {
                "uz": "Yig'ilib qolgan ishlarni tugataman",
                "ru": "Доделаю накопившиеся дела",
                "en": "Finish the tasks that piled up",
            }, {"tartib": 0.8}),
        ),
    ),
    Question(
        id="yangi_shahar",
        text={
            "uz": "Notanish shaharga tushdingiz. Birinchi nima qilasiz?",
            "ru": "Вы в незнакомом городе. Что сделаете первым делом?",
            "en": "You land in an unfamiliar city. What do you do first?",
        },
        answers=(
            Answer("xarita", {
                "uz": "Xaritani ochib marshrut tuzaman",
                "ru": "Открою карту и составлю маршрут",
                "en": "Open the map and plan a route",
            }, {"tartib": 0.9}),
            Answer("sayr", {
                "uz": "Maqsadsiz yuraveraman, o'zi topiladi",
                "ru": "Просто пойду гулять, само найдётся",
                "en": "Just wander — it will find me",
            }, {"tartib": -0.9, "yangilik": 0.5}),
            Answer("kafe", {
                "uz": "Kafe topib, odamlarni kuzataman",
                "ru": "Найду кафе и буду наблюдать за людьми",
                "en": "Find a cafe and watch people",
            }, {"sokinlik": 0.7, "davra": -0.3}),
            Answer("mahalliy", {
                "uz": "Mahalliylardan qayer qiziqligini so'rayman",
                "ru": "Спрошу у местных, где интересно",
                "en": "Ask locals where the fun is",
            }, {"davra": 0.7, "yangilik": 0.6}),
        ),
    ),
    Question(
        id="ovqat",
        text={
            "uz": "Restoranda ovqat tanlayotganda...",
            "ru": "Когда выбираете еду в ресторане...",
            "en": "When choosing food at a restaurant...",
        },
        answers=(
            Answer("tanish", {
                "uz": "Tanish taomni olaman, aldamaydi",
                "ru": "Возьму привычное блюдо, оно не подведёт",
                "en": "Take the familiar dish — it never disappoints",
            }, {"yangilik": -0.9}),
            Answer("tavsiya", {
                "uz": "Ofitsiant nimani maqtasa, shuni",
                "ru": "То, что посоветует официант",
                "en": "Whatever the waiter recommends",
            }, {"yangilik": 0.8, "tartib": -0.4}),
            Answer("menyu", {
                "uz": "Butun menyuni o'qib, sinchiklab tanlayman",
                "ru": "Прочитаю всё меню и выберу вдумчиво",
                "en": "Read the whole menu and choose carefully",
            }, {"tartib": 0.8}),
            Answer("hamma", {
                "uz": "Hamma nima olsa, men ham",
                "ru": "Что все — то и я",
                "en": "Whatever everyone else orders",
            }, {"davra": 0.8, "yangilik": -0.3}),
        ),
    ),
    Question(
        id="qaytish",
        text={
            "uz": "Sayohatdan qanday holatda qaytishni istaysiz?",
            "ru": "В каком состоянии хотите вернуться из поездки?",
            "en": "How do you want to feel coming back from a trip?",
        },
        answers=(
            Answer("dam", {
                "uz": "Yaxshi dam olgan, tetik holda",
                "ru": "Отдохнувшим и посвежевшим",
                "en": "Rested and refreshed",
            }, {"sokinlik": 1.0}),
            Answer("taassurot", {
                "uz": "Taassurotlarga to'lib",
                "ru": "Полным впечатлений",
                "en": "Full of impressions",
            }, {"yangilik": 0.9, "sokinlik": -0.6}),
            Answer("tanishlar", {
                "uz": "Yangi tanishlar orttirib",
                "ru": "С новыми знакомствами",
                "en": "With new acquaintances",
            }, {"davra": 1.0}),
            Answer("korilgan", {
                "uz": "Rejadagi hamma joyni ko'rib bo'lib",
                "ru": "Посмотрев всё, что было в плане",
                "en": "Having seen everything on the list",
            }, {"tartib": 0.9, "sokinlik": -0.5}),
        ),
    ),
    Question(
        id="charchatadi",
        text={
            "uz": "Sizni ko'proq nima charchatadi?",
            "ru": "Что вас утомляет сильнее?",
            "en": "What drains you more?",
        },
        answers=(
            Answer("shovqin", {
                "uz": "Shovqin va olomon",
                "ru": "Шум и толпа",
                "en": "Noise and crowds",
            }, {"davra": -0.9, "sokinlik": 0.4}),
            Answer("kutish", {
                "uz": "Uzoq kutish va bekorchilik",
                "ru": "Долгое ожидание и безделье",
                "en": "Long waits and idleness",
            }, {"sokinlik": -0.9}),
            Answer("ozgarish", {
                "uz": "Kutilmagan o'zgarishlar",
                "ru": "Неожиданные перемены",
                "en": "Unexpected changes",
            }, {"tartib": 0.9, "yangilik": -0.4}),
            Answer("bir_xillik", {
                "uz": "Har kuni bir xillik",
                "ru": "Однообразие изо дня в день",
                "en": "The same thing every day",
            }, {"yangilik": 0.9, "tartib": -0.3}),
        ),
    ),
    Question(
        id="byudjet",
        text={
            "uz": "Byudjet cheklangan. Nimadan voz kechasiz?",
            "ru": "Бюджет ограничен. От чего откажетесь?",
            "en": "Budget is tight. What do you give up?",
        },
        answers=(
            Answer("mehmonxona", {
                "uz": "Qulay mehmonxonadan — ko'p joy ko'rsam bo'ldi",
                "ru": "От комфортного отеля — лишь бы увидеть больше",
                "en": "The comfortable hotel — I just want to see more",
            }, {"sokinlik": -0.8, "yangilik": 0.6}),
            Answer("ekskursiya", {
                "uz": "Ekskursiyalardan — asosiysi yaxshi dam olish",
                "ru": "От экскурсий — главное хорошо отдохнуть",
                "en": "The excursions — resting well matters most",
            }, {"sokinlik": 0.9}),
            Answer("uzoq", {
                "uz": "Uzoq parvozdan — yaqinroq joy ham bo'ladi",
                "ru": "От дальнего перелёта — сойдёт и поближе",
                "en": "The long flight — somewhere closer will do",
            }, {"yangilik": -0.6, "tartib": 0.4}),
            Answer("kechiktirish", {
                "uz": "Hech nimadan — sayohatni keyinga qoldiraman",
                "ru": "Ни от чего — лучше отложу поездку",
                "en": "Nothing — I would rather postpone the trip",
            }, {"tartib": 0.8, "yangilik": -0.3}),
        ),
    ),
    Question(
        id="surat",
        text={
            "uz": "Sayohatda suratga olasizmi?",
            "ru": "Фотографируете ли вы в поездке?",
            "en": "Do you take photos when travelling?",
        },
        answers=(
            Answer("kop", {
                "uz": "Ko'p — har lahzani saqlab qolaman",
                "ru": "Много — сохраняю каждый момент",
                "en": "A lot — I save every moment",
            }, {"davra": 0.6, "yangilik": 0.4}),
            Answer("kam", {
                "uz": "Kam — lahzani yashamoqchiman",
                "ru": "Мало — хочу проживать момент",
                "en": "Few — I want to live the moment",
            }, {"sokinlik": 0.7}),
            Answer("manzara", {
                "uz": "Faqat manzaralarni",
                "ru": "Только пейзажи",
                "en": "Landscapes only",
            }, {"davra": -0.6, "sokinlik": 0.4}),
            Answer("oylamayman", {
                "uz": "Bu haqda o'ylamayman ham",
                "ru": "Даже не думаю об этом",
                "en": "I do not even think about it",
            }, {"tartib": -0.7}),
        ),
    ),
)

QUESTION_BY_ID = {q.id: q for q in QUESTIONS}
_ANSWER_BY_ID = {(q.id, a.id): a for q in QUESTIONS for a in q.answers}


@dataclass(frozen=True)
class TravelProfile:
    """To'rtta o'lcham, har biri 0..1."""

    scores: dict[Dimension, float]
    answered: int

    def get(self, dim: Dimension) -> float:
        return self.scores.get(dim, 0.5)

    def to_dict(self) -> dict:
        return {"scores": dict(self.scores), "answered": self.answered}


def score(answers: dict[str, str]) -> TravelProfile:
    """Javoblardan profil hisoblaydi.

    `answers` — {savol_id: javob_id}. Noma'lum kalitlar JIMGINA
    tashlanadi: mijoz eski ilova versiyasidan yuborgan savol o'chirilgan
    bo'lishi mumkin va bu butun anketani yiqitmasligi kerak.

    Javob berilmagan o'lcham 0.5 (betaraf) bo'lib qoladi — nol emas,
    aks holda javob bermaslik "tinchlikni umuman istamayman" degan
    kuchli signalga aylanardi.
    """
    xom: dict[Dimension, float] = {d: 0.0 for d in DIMENSIONS}
    # Har o'lcham bo'yicha necha marta ovoz berilganini alohida sanaymiz:
    # bir o'lchamga 5 ta savol, boshqasiga 1 ta tegsa, ularni bir xil
    # bo'luvchiga bo'lish kamroq tegilganini sun'iy ravishda betarafga
    # tortib qo'yardi.
    ogirlik: dict[Dimension, float] = {d: 0.0 for d in DIMENSIONS}

    berilgan = 0
    for savol_id, javob_id in (answers or {}).items():
        javob = _ANSWER_BY_ID.get((savol_id, javob_id))
        if javob is None:
            continue
        berilgan += 1
        for dim, w in javob.weights.items():
            xom[dim] += w
            ogirlik[dim] += abs(w)

    natija: dict[Dimension, float] = {}
    for d in DIMENSIONS:
        if ogirlik[d] == 0:
            natija[d] = 0.5
        else:
            # -1..+1 -> 0..1
            natija[d] = round((xom[d] / ogirlik[d] + 1) / 2, 3)
    return TravelProfile(scores=natija, answered=berilgan)


@dataclass(frozen=True)
class Preference:
    """Profildan chiqqan tavsiya mezonlari."""

    categories: tuple[TourCategory, ...]
    boards: tuple[Board, ...]
    booking_type: str          # "group" yoki "individual"
    min_days: int
    max_days: int
    # Tushuntirish — mijozga NEGA shunday tavsiya qilinganini aytamiz.
    # "Qora quti" tavsiya ishonchsiz ko'rinadi.
    reasons: tuple[str, ...]


_HIGH = 0.62
_LOW = 0.38


def to_preference(profile: TravelProfile) -> Preference:
    """Profilni tur mezonlariga aylantiradi.

    Qoidalar ochiq va sinaladi: bu yerda o'rganuvchi model yo'q. Model
    keyingi qadamda — mijoz qaysi tavsiyani bron qilgani bo'yicha
    (`recommendation_events`) ballar sozlanadi.
    """
    sokin = profile.get("sokinlik")
    yangi = profile.get("yangilik")
    davra = profile.get("davra")
    tartib = profile.get("tartib")

    toifalar: list[TourCategory] = []
    sabablar: list[str] = []

    if sokin >= _HIGH:
        toifalar += [TourCategory.BEACH, TourCategory.MEDICAL]
        sabablar.append("dam_olish")
    if sokin <= _LOW:
        toifalar += [TourCategory.EXCURSION, TourCategory.SKI]
        sabablar.append("harakat")
    if yangi >= _HIGH:
        toifalar += [TourCategory.EXCURSION, TourCategory.CRUISE]
        sabablar.append("yangilik")
    if yangi <= _LOW:
        toifalar += [TourCategory.BEACH]
        sabablar.append("tanish")
    if davra >= _HIGH:
        toifalar += [TourCategory.SHOPPING, TourCategory.BEACH]
        sabablar.append("davra")
    if davra <= _LOW:
        toifalar += [TourCategory.MEDICAL]
        sabablar.append("tinchlik")

    if not toifalar:
        # Hamma o'lcham betaraf — eng keng tarqalgan ikkitasi.
        toifalar = [TourCategory.BEACH, TourCategory.EXCURSION]
        sabablar.append("betaraf")

    # Takrorlarni olib tashlaymiz, lekin TARTIBNI saqlaymiz: birinchi
    # qo'shilgan toifa eng kuchli signaldan chiqqan.
    korilgan: set[TourCategory] = set()
    tartibli: list[TourCategory] = []
    for t in toifalar:
        if t not in korilgan:
            korilgan.add(t)
            tartibli.append(t)

    # Ovqatlanish. Tinchlik qidirgan odam mehmonxonadan chiqmaydi,
    # harakatdagi odam esa kun bo'yi tashqarida — unga AI ortiqcha pul.
    if sokin >= _HIGH:
        boards = (Board.AI, Board.UAI, Board.FB)
    elif sokin <= _LOW:
        boards = (Board.BB, Board.HB)
    else:
        boards = (Board.HB, Board.AI, Board.BB)

    # Guruh yoki individual. Reja sevuvchi odamga tayyor guruh turi
    # qulay; erkinlik sevuvchiga u qafas bo'lib tuyuladi.
    booking_type = "group" if tartib >= _HIGH else (
        "individual" if tartib <= _LOW else "group"
    )
    if tartib >= _HIGH:
        sabablar.append("reja")
    elif tartib <= _LOW:
        sabablar.append("erkinlik")

    # Davomiylik. Dam olish uchun qisqa sayohat yetmaydi; ko'p joy
    # ko'rmoqchi bo'lgan odam esa uzoq bir joyda o'tirmaydi.
    if sokin >= _HIGH:
        min_days, max_days = 7, 14
    elif sokin <= _LOW:
        min_days, max_days = 3, 10
    else:
        min_days, max_days = 5, 12

    return Preference(
        categories=tuple(tartibli),
        boards=boards,
        booking_type=booking_type,
        min_days=min_days,
        max_days=max_days,
        reasons=tuple(dict.fromkeys(sabablar)),
    )


REASON_TEXT: dict[str, dict[str, str]] = {
    "dam_olish": {
        "uz": "Javoblaringizdan ko'rinishicha sizga tinch dam olish kerak",
        "ru": "По ответам видно, что вам нужен спокойный отдых",
        "en": "Your answers point to a calm, restful trip",
    },
    "harakat": {
        "uz": "Siz bir joyda o'tirishni yoqtirmaysiz",
        "ru": "Вам не сидится на одном месте",
        "en": "You do not like sitting still",
    },
    "yangilik": {
        "uz": "Yangi joy va yangi taassurot sizni quvvatlaydi",
        "ru": "Новые места и впечатления вас заряжают",
        "en": "New places and impressions energise you",
    },
    "tanish": {
        "uz": "Siz sinalgan, ishonchli variantni afzal ko'rasiz",
        "ru": "Вы предпочитаете проверенный вариант",
        "en": "You prefer the tried and tested",
    },
    "davra": {
        "uz": "Davra va jonli muhit siz uchun muhim",
        "ru": "Вам важна компания и живая атмосфера",
        "en": "Company and a lively atmosphere matter to you",
    },
    "tinchlik": {
        "uz": "Shovqindan uzoq joy sizga ko'proq yoqadi",
        "ru": "Вам больше подойдёт место подальше от шума",
        "en": "Somewhere away from the noise suits you better",
    },
    "reja": {
        "uz": "Hammasi oldindan rejalashtirilgan bo'lgani ma'qul",
        "ru": "Лучше, когда всё спланировано заранее",
        "en": "Better when everything is planned in advance",
    },
    "erkinlik": {
        "uz": "Qattiq jadval sizni bo'g'adi",
        "ru": "Жёсткий график вас сковывает",
        "en": "A rigid schedule holds you back",
    },
    "betaraf": {
        "uz": "Eng ko'p tanlanadigan yo'nalishlardan boshladik",
        "ru": "Начали с самых популярных направлений",
        "en": "We started from the most popular options",
    },
}


def questions_payload(lang: str = "uz") -> list[dict]:
    """Anketani mijoz uchun tayyorlaydi.

    Noma'lum til uchun o'zbekchaga tushamiz — bo'sh matn ko'rsatishdan
    ko'ra tushunarli til yaxshiroq.
    """
    til = lang if lang in ("uz", "ru", "en") else "uz"
    return [
        {
            "id": q.id,
            "text": q.text.get(til, q.text["uz"]),
            "answers": [
                {"id": a.id, "text": a.text.get(til, a.text["uz"])}
                for a in q.answers
            ],
        }
        for q in QUESTIONS
    ]


def explain(pref: Preference, lang: str = "uz") -> list[str]:
    """Tavsiya sabablarini mijoz tilida qaytaradi."""
    til = lang if lang in ("uz", "ru", "en") else "uz"
    return [
        REASON_TEXT[r].get(til, REASON_TEXT[r]["uz"])
        for r in pref.reasons
        if r in REASON_TEXT
    ]
