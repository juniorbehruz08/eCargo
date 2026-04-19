from decimal import Decimal
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class PendingUser(models.Model):
    email = models.EmailField()
    username = models.CharField(max_length=150)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    password = models.CharField(max_length=255)
    code = models.CharField(max_length=6)
    role = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=10)

    def __str__(self):
        return f"{self.email} ({self.username})"


class Role(models.Model):
    ROLE_CHOICES = [
        ('shipper', 'Shipper'),
        ('carrier', 'Carrier'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='user_role')
    role = models.CharField(max_length=100, choices=ROLE_CHOICES)

    def __str__(self):
        return f"{self.user.username} - {self.role}"


# NEW: User status 1-100
class UserStatus(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='status')
    score = models.PositiveIntegerField(default=50)  # 1-100

    def __str__(self):
        return f"{self.user.username} — {self.score}/100"

    def clean(self):
        if not (1 <= self.score <= 100):
            raise ValidationError({'score': 'Score must be between 1 and 100.'})

    @property
    def label(self):
        if self.score >= 80:
            return 'Trusted'
        elif self.score >= 50:
            return 'Good'
        elif self.score >= 30:
            return 'Average'
        return 'Low'

    @property
    def color(self):
        if self.score >= 80:
            return 'green'
        elif self.score >= 50:
            return 'yellow'
        return 'red'


class Load(models.Model):
    BODY_TYPE_CHOICES = [
        ('curtainsider', 'Curtainsider'),
        ('tautliner', 'Tautliner'),
        ('flatbed', 'Flatbed'),
        ('box', 'Box / Closed'),
        ('refrigerated', 'Refrigerated'),
        ('tanker', 'Tanker'),
        ('lowloader', 'Low Loader'),
        ('tipper', 'Tipper'),
        ('container', 'Container'),
        ('other', 'Other'),
    ]

    LOAD_TYPE_CHOICES = [
        ('FTL', 'FTL - Full Truck Load'),
        ('LTL', 'LTL - Less than Truck Load'),
    ]

    PUBLICATION_MODE_CHOICES = [
        ('exchange', 'Exchange'),
        ('selected', 'To Selected'),
    ]

    CURRENCY_CHOICES = [
        ('USD', 'USD'),
        ('EUR', 'EUR'),
        ('GBP', 'GBP'),
        ('PLN', 'PLN'),
        ('CZK', 'CZK'),
    ]

    VEHICLE_SIZE_CHOICES = [
        ('semi', 'With Semi-Trailer'),
        ('solo', 'Solo'),
        ('van', 'Van'),
        ('double', 'With Double Trailer'),
    ]

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='loads'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    publication_mode = models.CharField(max_length=20, choices=PUBLICATION_MODE_CHOICES, default='exchange')
    time_to_submit_offers = models.DateTimeField(null=True, blank=True)
    contacts = models.CharField(max_length=255, blank=True)
    buy_now = models.BooleanField(default=False)
    schedule_publication = models.BooleanField(default=False)
    scheduled_publish_at = models.DateTimeField(null=True, blank=True)

    total_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=5, choices=CURRENCY_CHOICES, default='USD')
    mileage = models.FloatField(null=True, blank=True)
    price_per_mile = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payment_deadline_days = models.PositiveIntegerField(null=True, blank=True)

    vehicle_size = models.CharField(max_length=20, choices=VEHICLE_SIZE_CHOICES, blank=True)
    body_type = models.CharField(max_length=30, choices=BODY_TYPE_CHOICES, blank=True)
    capacity = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    load_meters = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    load_type = models.CharField(max_length=3, choices=LOAD_TYPE_CHOICES, default='FTL')
    quantity = models.IntegerField(null=True, blank=True)
    stackable = models.BooleanField(default=False)
    to_exchange = models.BooleanField(default=False)
    additional_description = models.TextField(blank=True, max_length=2000)

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        pickup = self.locations.filter(location_type='pickup').first()
        delivery = self.locations.filter(location_type='delivery').first()
        return f"Load #{self.pk} | {pickup} → {delivery}"

    def clean(self):
        if self.mileage is not None and self.mileage < 0:
            raise ValidationError({'mileage': 'Mileage cannot be negative.'})
        if self.total_price is not None and self.total_price < 0:
            raise ValidationError({'total_price': 'Total price cannot be negative.'})
        if self.payment_deadline_days is not None and self.payment_deadline_days < 0:
            raise ValidationError({'payment_deadline_days': 'Payment deadline cannot be negative.'})

    def save(self, *args, **kwargs):
        if self.total_price is not None and self.mileage not in (None, 0):
            self.price_per_mile = (
                Decimal(str(self.total_price)) / Decimal(str(self.mileage))
            ).quantize(Decimal('0.01'))
        else:
            self.price_per_mile = None
        super().save(*args, **kwargs)

    @property
    def pickup_datetime(self):
        loc = self.locations.filter(location_type='pickup').first()
        return loc.date_from if loc else None

    @property
    def hours_until_pickup(self):
        pickup_dt = self.pickup_datetime
        if not pickup_dt:
            return None
        delta = pickup_dt - timezone.now()
        return delta.total_seconds() / 3600

    @property
    def color_status(self):
        hours = self.hours_until_pickup
        if hours is None:
            return 'white'
        if hours < 0:
            return 'gray'
        elif hours <= 24:
            return 'red'
        elif hours <= 48:
            return 'yellow'
        elif hours <= 72:
            return 'green'
        return 'white'

    @property
    def color_label(self):
        hours = self.hours_until_pickup
        if hours is None:
            return 'Unknown'
        if hours < 0:
            return 'Expired'
        elif hours <= 24:
            return f'{int(hours)}h (Urgent)'
        elif hours <= 48:
            return f'{int(hours)}h (Soon)'
        elif hours <= 72:
            return f'{int(hours)}h (Normal)'
        return f'{int(hours)}h (Plenty of time)'


class LoadLocation(models.Model):
    LOCATION_TYPE_CHOICES = [
        ('pickup', 'Pickup'),
        ('delivery', 'Delivery'),
    ]

    load = models.ForeignKey(Load, on_delete=models.CASCADE, related_name='locations')
    location_type = models.CharField(max_length=10, choices=LOCATION_TYPE_CHOICES)

    country = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=200)
    full_address = models.CharField(max_length=500, blank=True)

    date_from = models.DateTimeField()
    date_to = models.DateTimeField(null=True, blank=True)
    is_range = models.BooleanField(default=False)

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(
                fields=['load', 'location_type'],
                name='unique_pickup_delivery_per_load'
            )
        ]

    def __str__(self):
        return f"{self.get_location_type_display()} - {self.country} {self.postal_code} {self.city}"


# NEW: Interest model — carrier expresses interest in a load
class Interest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]

    load = models.ForeignKey(Load, on_delete=models.CASCADE, related_name='interests')
    carrier = models.ForeignKey(User, on_delete=models.CASCADE, related_name='interests_sent')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    message = models.TextField(blank=True, max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['load', 'carrier'],
                name='unique_interest_per_load_carrier'
            )
        ]

    def __str__(self):
        return f"{self.carrier.username} → Load #{self.load.pk} ({self.status})"


# NEW: Notification model
class Notification(models.Model):
    TYPE_CHOICES = [
        ('interest', 'New Interest'),
        ('accepted', 'Interest Accepted'),
        ('rejected', 'Interest Rejected'),
        ('message', 'New Message'),
    ]

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='notifications_sent')
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    interest = models.ForeignKey(Interest, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    text = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notif → {self.recipient.username}: {self.notification_type}"


# NEW: ChatRoom — created when shipper accepts an interest
class ChatRoom(models.Model):
    interest = models.OneToOneField(Interest, on_delete=models.CASCADE, related_name='chat_room')
    shipper = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_rooms_as_shipper')
    carrier = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_rooms_as_carrier')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Chat: {self.shipper.username} ↔ {self.carrier.username} (Load #{self.interest.load.pk})"


# NEW: ChatMessage
class ChatMessage(models.Model):
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_messages')
    text = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.sender.username}: {self.text[:50]}"