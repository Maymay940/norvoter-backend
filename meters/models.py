from django.db import models


class User(models.Model):
    username = models.CharField("Имя пользователя", max_length=100, unique=True, db_column="username")
    email = models.EmailField("Email", unique=True, db_column="email")
    first_name = models.CharField("Имя", max_length=100, blank=True, db_column="first_name")
    last_name = models.CharField("Фамилия", max_length=100, blank=True, db_column="last_name")
    phone = models.CharField("Телефон", max_length=20, blank=True, db_column="phone")
    is_active = models.BooleanField("Активен", default=True, db_column="is_active")
    created_at = models.DateTimeField("Дата регистрации", auto_now_add=True, db_column="created_at")
    is_admin = models.BooleanField('Администратор', default=False)

    def __str__(self):
        return f"{self.username} ({self.first_name} {self.last_name})"

    class Meta:
        db_table = "users"
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"


class WaterMeter(models.Model):
    HOT = "HOT"
    COLD = "COLD"
    METER_TYPES = [
        (HOT, "ГВС"),
        (COLD, "ХВС"),
    ]

    user = models.ForeignKey(User, on_delete=models.RESTRICT, related_name="meters", db_column="user_id")
    address = models.CharField("Адрес", max_length=255, db_column="address")
    serial_number = models.CharField("Заводской номер", max_length=50, unique=True, db_column="serial_number")
    meter_type = models.CharField("Тип", max_length=10, choices=METER_TYPES, db_column="meter_type")
    meter_model = models.CharField("Модель", max_length=100, db_column="meter_model")
    installation_date = models.DateField("Дата установки", db_column="installation_date")
    initial_reading = models.IntegerField("Начальные показания", default=0, db_column="initial_reading")
    last_verified_reading = models.IntegerField("Последние показания", default=0, db_column="last_verified_reading")
    last_reading_date = models.DateField(
        "Дата последних показаний", null=True, blank=True, db_column="last_reading_date"
    )
    next_verification_date = models.DateField(
        "Дата следующей поверки",
        null=True,
        blank=True,
        db_column="next_verification_date",
    )
    photo_url = models.URLField("Фото", blank=True, null=True, db_column="photo_url")
    setup_video_url = models.URLField("Видео", blank=True, null=True, db_column="setup_video_url")
    is_active = models.BooleanField("Активен", default=True, db_column="is_active")
    created_at = models.DateTimeField("Дата добавления", auto_now_add=True, db_column="created_at")
    updated_at = models.DateTimeField("Дата обновления", auto_now=True, db_column="updated_at")

    def __str__(self):
        type_display = "ГВС" if self.meter_type == "HOT" else "ХВС"
        return f"{self.address} - {type_display} ({self.serial_number})"

    class Meta:
        db_table = "water_meters"
        verbose_name = "Счетчик"
        verbose_name_plural = "Счетчики"
        indexes = [
            models.Index(fields=["user", "address"]),
            models.Index(fields=["serial_number"]),
        ]


class Request(models.Model):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    REJECTED = "rejected"
    DELETED = "deleted"

    STATUS_CHOICES = [
        (DRAFT, "Черновик"),
        (SUBMITTED, "Отправлено"),
        (COMPLETED, "Завершено"),
        (REJECTED, "Отклонено"),
        (DELETED, "Удалено"),
    ]

    user = models.ForeignKey(User, on_delete=models.RESTRICT, related_name="requests", db_column="user_id")
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=STATUS_CHOICES,
        default=DRAFT,
        db_column="status",
    )
    created_at = models.DateTimeField("Дата создания", auto_now_add=True, db_column="created_at")
    submitted_at = models.DateTimeField("Дата отправки", null=True, blank=True, db_column="submitted_at")
    completed_at = models.DateTimeField("Дата завершения", null=True, blank=True, db_column="completed_at")
    total_consumption = models.DecimalField(
        "Общий расход",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        db_column="total_consumption",
    )
    amount_to_pay = models.DecimalField(
        "Сумма к оплате",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        db_column="amount_to_pay",
    )
    comment = models.TextField("Комментарий", blank=True, db_column="comment")

    def __str__(self):
        return f"Заявка №{self.id} ({self.get_status_display()})"

    class Meta:
        db_table = "requests"
        verbose_name = "Заявка"
        verbose_name_plural = "Заявки"
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["-created_at"]),
        ]


class ReadingPosition(models.Model):
    request = models.ForeignKey(
        Request,
        on_delete=models.RESTRICT,
        related_name="positions",
        db_column="request_id",
    )
    water_meter = models.ForeignKey(
        WaterMeter,
        on_delete=models.RESTRICT,
        related_name="readings",
        db_column="water_meter_id",
    )
    current_reading = models.IntegerField("Текущие показания", db_column="current_reading")
    consumption = models.IntegerField("Расход", db_column="consumption")
    reading_photo_url = models.URLField("Фото показаний", blank=True, null=True, db_column="reading_photo_url")
    created_at = models.DateTimeField("Дата добавления", auto_now_add=True, db_column="created_at")

    def __str__(self):
        return f"{self.water_meter.address} - {self.current_reading} м³"

    class Meta:
        db_table = "reading_positions"
        verbose_name = "Позиция"
        verbose_name_plural = "Позиции"
        unique_together = ["request", "water_meter"]
        indexes = [
            models.Index(fields=["request", "water_meter"]),
        ]
