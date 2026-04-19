from django.contrib import admin
from .models import PendingUser, Role, Load, LoadLocation, UserStatus


@admin.register(PendingUser)
class PendingUserAdmin(admin.ModelAdmin):
    list_display = (
        'email',
        'username',
        'first_name',
        'last_name',
        'role',
        'code',
        'created_at',
        'expired_status',
    )
    search_fields = (
        'email',
        'username',
        'first_name',
        'last_name',
        'role',
        'code',
    )
    list_filter = ('role', 'created_at')
    readonly_fields = ('created_at', 'expired_status')
    ordering = ('-created_at',)

    @admin.display(description='Expired')
    def expired_status(self, obj):
        return obj.is_expired()


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('user', 'role')
    search_fields = ('user__username', 'user__email', 'role')
    list_filter = ('role',)
    raw_id_fields = ('user',)


class LoadLocationInline(admin.TabularInline):
    model = LoadLocation
    extra = 0
    fields = (
        'location_type',
        'country',
        'postal_code',
        'city',
        'full_address',
        'date_from',
        'date_to',
        'is_range',
    )


@admin.register(Load)
class LoadAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'route_display',
        'created_by',
        'publication_mode',
        'load_type',
        'vehicle_size',
        'body_type',
        'total_price',
        'currency',
        'mileage',
        'price_per_mile',
        'pickup_time',
        'color_status_badge',
        'is_active',
        'created_at',
    )
    list_filter = (
        'is_active',
        'publication_mode',
        'load_type',
        'vehicle_size',
        'body_type',
        'currency',
        'buy_now',
        'schedule_publication',
        'stackable',
        'to_exchange',
        'created_at',
    )
    search_fields = (
        'id',
        'contacts',
        'additional_description',
        'created_by__username',
        'created_by__email',
        'locations__country',
        'locations__city',
        'locations__postal_code',
        'locations__full_address',
    )
    readonly_fields = (
        'created_at',
        'updated_at',
        'price_per_mile',
        'hours_until_pickup_display',
        'color_status_badge',
        'color_label_display',
    )
    raw_id_fields = ('created_by',)
    inlines = [LoadLocationInline]
    ordering = ('-created_at',)

    fieldsets = (
        ('Main info', {
            'fields': (
                'created_by',
                'is_active',
            )
        }),
        ('Publication', {
            'fields': (
                'publication_mode',
                'time_to_submit_offers',
                'contacts',
                'buy_now',
                'schedule_publication',
                'scheduled_publish_at',
            )
        }),
        ('Pricing', {
            'fields': (
                'total_price',
                'currency',
                'mileage',
                'price_per_mile',
                'payment_deadline_days',
            )
        }),
        ('Vehicle requirements', {
            'fields': (
                'vehicle_size',
                'body_type',
                'capacity',
                'load_meters',
                'load_type',
                'quantity',
                'stackable',
                'to_exchange',
            )
        }),
        ('Description', {
            'fields': ('additional_description',)
        }),
        ('Computed status', {
            'fields': (
                'hours_until_pickup_display',
                'color_status_badge',
                'color_label_display',
            )
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at',
            )
        }),
    )

    @admin.display(description='Route')
    def route_display(self, obj):
        pickup = obj.locations.filter(location_type='pickup').first()
        delivery = obj.locations.filter(location_type='delivery').first()

        pickup_text = f"{pickup.country}/{pickup.city}" if pickup else "—"
        delivery_text = f"{delivery.country}/{delivery.city}" if delivery else "—"

        return f"{pickup_text} → {delivery_text}"

    @admin.display(description='Pickup time')
    def pickup_time(self, obj):
        pickup = obj.locations.filter(location_type='pickup').first()
        return pickup.date_from if pickup else None

    @admin.display(description='Hours until pickup')
    def hours_until_pickup_display(self, obj):
        hours = obj.hours_until_pickup
        if hours is None:
            return "Unknown"
        return round(hours, 1)

    @admin.display(description='Color status')
    def color_status_badge(self, obj):
        return obj.color_status

    @admin.display(description='Color label')
    def color_label_display(self, obj):
        return obj.color_label


@admin.register(LoadLocation)
class LoadLocationAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'load',
        'location_type',
        'country',
        'postal_code',
        'city',
        'date_from',
        'date_to',
        'is_range',
    )
    list_filter = (
        'location_type',
        'is_range',
        'country',
        'date_from',
    )
    search_fields = (
        'load__id',
        'country',
        'postal_code',
        'city',
        'full_address',
    )
    raw_id_fields = ('load',)
    ordering = ('load', 'id')

@admin.register(UserStatus)
class UserStatusAdmin(admin.ModelAdmin):
    list_display = ('user', 'score')