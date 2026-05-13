import os
import sys
import django

# Ensure project root is in path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp.settings')
django.setup()

from common_v2.models import UserGuideSection, UserGuideContent
from accounts.models import ERPRole

def seed_user_guide():
    # 1. Overview Section
    overview, _ = UserGuideSection.objects.get_or_create(
        title_uz="Umumiy Ma'lumot",
        defaults={
            "title_ru": "Общая информация",
            "icon": "Layout",
            "order": 1
        }
    )
    
    UserGuideContent.objects.update_or_create(
        section=overview,
        title_uz="Yuksar Industrial ERP v2.4",
        defaults={
            "title_ru": "Yuksar Industrial ERP v2.4",
            "body_uz": "Yuksar ERP — bu korxonaning barcha biznes-jarayonlarini yagona ekotizimga birlashtiruvchi platforma. Tizimning asosiy maqsadi — inson omilini kamaytirish, xatoliklarni oldini olish va real vaqt rejimida aniq hisobotlarni taqdim etish.",
            "body_ru": "Yuksar ERP — это платформа, объединяющая все бизнес-процессы предприятия в единую экосистему. Основная цель системы — минимизация человеческого фактора, предотвращение ошибок и предоставление точной отчетности в реальном времени.",
            "order": 1
        }
    )

    # 2. Warehouse & Logistics
    warehouse, _ = UserGuideSection.objects.get_or_create(
        title_uz="1. Ombor va Logistika",
        defaults={
            "title_ru": "1. Склад и Логистика",
            "icon": "Database",
            "order": 2
        }
    )
    
    UserGuideContent.objects.update_or_create(
        section=warehouse,
        title_uz="Ombor Boshqaruvi",
        defaults={
            "title_ru": "Управление Складом",
            "body_uz": "Tizimda 4 ta asosiy ombor mavjud: Sklad 1 (Xom-ashyo), Sklad 2 (Tayyor bloklar), Sklad 3 (Yarim tayyor), Sklad 4 (Tayyor mahsulot). Har bir ombor o'zining mas'ul shaxsiga ega.",
            "body_ru": "В системе есть 4 основных склада: Склад 1 (Сырье), Склад 2 (Готовые блоки), Склад 3 (Полуфабрикаты), Склад 4 (Готовая продукция). У каждого склада есть свое ответственное лицо.",
            "order": 1
        }
    )

    # 3. Production
    production, _ = UserGuideSection.objects.get_or_create(
        title_uz="2. Ishlab Chiqarish",
        defaults={
            "title_ru": "2. Производство",
            "icon": "Factory",
            "order": 3
        }
    )
    
    UserGuideContent.objects.update_or_create(
        section=production,
        title_uz="Ishlab Chiqarish Zanjiri",
        defaults={
            "title_ru": "Производственная цепочка",
            "body_uz": "Jarayon: Order yaratiladi -> Zames (Retsept bo'yicha) -> Formovka -> Sklad 2 (Yetilish) -> CNC (Kesish) -> QC (Sifat nazorati) -> Sklad 4.",
            "body_ru": "Процесс: Создание ордера -> Замес (по рецепту) -> Формовка -> Склад 2 (Созревание) -> CNC (Резка) -> QC (Контроль качества) -> Склад 4.",
            "order": 1
        }
    )

    # 4. Sales & CRM
    sales_crm, _ = UserGuideSection.objects.get_or_create(
        title_uz="3. Sotuv va CRM",
        defaults={
            "title_ru": "3. Продажи и CRM",
            "icon": "ShoppingBag",
            "order": 4
        }
    )
    
    UserGuideContent.objects.update_or_create(
        section=sales_crm,
        title_uz="Mijozlar va Leadlar",
        defaults={
            "title_ru": "Клиенты и Лиды",
            "body_uz": "Har bir mijoz uchun alohida karta mavjud. Leadlar - bu potentsial mijozlar bo'lib, ularni 'WON' statusiga o'tkazish orqali sotuvni amalga oshirish mumkin.",
            "body_ru": "Для каждого клиента есть отдельная карточка. Лиды — это потенциальные клиенты, совершение продажи возможно путем перевода их в статус 'WON'.",
            "order": 1
        }
    )

    # 5. Finance & Analytics
    finance, _ = UserGuideSection.objects.get_or_create(
        title_uz="4. Moliya va Analitika",
        defaults={
            "title_ru": "4. Финансы и Аналитика",
            "icon": "BarChart3",
            "order": 5
        }
    )
    
    UserGuideContent.objects.update_or_create(
        section=finance,
        title_uz="P&L va Foyda Tahlili",
        defaults={
            "title_ru": "P&L и анализ прибыли",
            "body_uz": "Xarajatlarni (P&L) tahlil qilish orqali har bir mahsulotning sof foydasini ko'rish mumkin. Shuningdek, xodimlarning ishbay maoshlari ishlab chiqarish natijalariga ko'ra hisoblanadi.",
            "body_ru": "Через анализ расходов (P&L) можно увидеть чистую прибыль каждого продукта. Также сдельная зарплата сотрудников рассчитывается на основе результатов производства.",
            "order": 1
        }
    )

    # 6. Roles
    roles_sec, _ = UserGuideSection.objects.get_or_create(
        title_uz="5. Xodimlar Rollari",
        defaults={
            "title_ru": "5. Роли сотрудников",
            "icon": "UserCheck",
            "order": 6
        }
    )
    
    roles_to_seed = [
        ('Bosh Admin', "Barcha modullarga to'liq ruxsat. Moliya va foyda hisobotlari.", "Полный доступ ко всем модулям. Финансовые отчеты."),
        ('Sotuv menejeri', "Mijozlar bazasi va Leadlar bilan ishlash. Yangi sotuvlarni rasmiylashtirish.", "Работа с базой клиентов и лидами. Оформление продаж."),
        ('Omborchi', "Xom-ashyo qabul qilish va tarqatish. Ombor qoldiqlarini nazorat qilish.", "Приемка и распределение сырья. Контроль складских остатков."),
        ('Ishlab chiqarish ustasi', "Ishlab chiqarish naryadlarini boshqarish va jarayon nazorati.", "Управление производственными нарядами и контроль процесса."),
        ('CNC operatori', "Kesish topshiriqlarini bajarish va bloklar sarfini qayd etish.", "Выполнение заданий по резке и регистрация расхода блоков."),
        ('Kuryer', "Yetkazib berish topshiriqlari va yukni topshirishni tasdiqlash.", "Задания на доставку и подтверждение сдачи груза."),
    ]

    for i, (role_name, uz_body, ru_body) in enumerate(roles_to_seed):
        role_obj = ERPRole.objects.filter(name=role_name).first()
        UserGuideContent.objects.update_or_create(
            section=roles_sec,
            role=role_obj,
            title_uz=f"{role_name} Qo'llanmasi",
            defaults={
                "title_ru": f"Руководство: {role_name}",
                "body_uz": uz_body,
                "body_ru": ru_body,
                "order": i + 1
            }
        )

    # 7. Settings
    settings_sec, _ = UserGuideSection.objects.get_or_create(
        title_uz="6. Tizim Sozlamalari",
        defaults={
            "title_ru": "6. Настройки системы",
            "icon": "Settings",
            "order": 7
        }
    )
    
    UserGuideContent.objects.update_or_create(
        section=settings_sec,
        title_uz="Audit va Xavfsizlik",
        defaults={
            "title_ru": "Аудит и безопасность",
            "body_uz": "Tizimda har bir login, ma'lumot o'zgarishi va pul operatsiyasi audit jurnali (logs) da saqlanadi. Administratorlar faoliyatni real vaqtda kuzatishi mumkin.",
            "body_ru": "В системе каждое действие, вход и финансовая операция сохраняются в журнале аудита (логи). Администраторы могут следить за деятельностью в реальном времени.",
            "order": 1
        }
    )

    print("Comprehensive User Guide Seeded successfully!")

if __name__ == "__main__":
    seed_user_guide()
