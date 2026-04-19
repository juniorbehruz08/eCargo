import json

from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from .forms import LoginForm
from .models import (
    ChatMessage, ChatRoom, Interest, Load, LoadLocation,
    Notification, PendingUser, Role, UserStatus,
)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def get_user_role(user):
    """Return 'shipper', 'carrier', or None."""
    try:
        return user.user_role.role
    except Exception:
        return None


def unread_notification_count(user):
    return Notification.objects.filter(recipient=user, is_read=False).count()


# ──────────────────────────────────────────────
# Auth views
# ──────────────────────────────────────────────

def main(request):
    return render(request, 'main.html')


def send_code(request):
    from django.contrib.auth.hashers import make_password
    from random import randint

    data = json.loads(request.body)
    code = randint(100000, 999999)

    PendingUser.objects.filter(email=data['email']).delete()
    # 'country' key is sent by the registration form (mislabeled field — actually the role selector)
    role_raw = data.get('role') or data.get('country', '')
    PendingUser.objects.create(
        email=data['email'],
        username=data['username'],
        first_name=data['first_name'],
        last_name=data['last_name'],
        password=make_password(data['password']),
        code=str(code),
        role=role_raw.lower(),  # normalise to lowercase to match Role.ROLE_CHOICES
    )

    send_mail(
        "Math Academy",
        f"Your code: {code}",
        "botbexruz640@gmail.com",
        [data['email']],
        fail_silently=False,
    )
    return JsonResponse({"success": True})


def verify_email(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        code = data.get('code', '').strip()
        email = data.get('email', '').strip()

        try:
            pending = PendingUser.objects.get(email=email, code=code)
        except PendingUser.DoesNotExist:
            return JsonResponse({'error': 'Invalid or expired code.'}, status=400)

        if pending.is_expired():
            pending.delete()
            return JsonResponse({'error': 'Code expired. Request a new one.'}, status=400)

        if User.objects.filter(username=pending.username).exists():
            return JsonResponse({'error': 'Username already taken.'}, status=400)

        user = User.objects.create_user(
            username=pending.username,
            email=pending.email,
            first_name=pending.first_name,
            last_name=pending.last_name,
        )
        user.password = pending.password
        user.save()

        Role.objects.create(role=pending.role, user=user)
        UserStatus.objects.create(user=user, score=50)  # default status
        pending.delete()

        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return JsonResponse({'success': True, 'redirect': '/load_list/'})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def login_view(request):
    if request.method == 'POST':
        if request.POST.get('type') == 'login':
            form = LoginForm(data=request.POST)
            if form.is_valid():
                username = request.POST.get('username')
                password = request.POST.get('password')
                user = authenticate(request, username=username, password=password)
                if user and user.is_active:
                    login(request, user)
                    return redirect('load_list')
            return redirect('login')
        return redirect('login')

    return render(request, "login_and_register.html", {'title': 'Login'})


# ──────────────────────────────────────────────
# Load list & detail
# ──────────────────────────────────────────────

@login_required
def load_list(request):
    loads = Load.objects.filter(is_active=True).prefetch_related('locations', 'interests')
    role = get_user_role(request.user)

    # For each load: has this carrier already expressed interest?
    carrier_interests = {}
    if role == 'carrier':
        my_interests = Interest.objects.filter(carrier=request.user).values_list('load_id', 'status')
        carrier_interests = {load_id: status for load_id, status in my_interests}

    loads_with_status = []
    for load in loads:
        pickup_loc = load.locations.filter(location_type='pickup').first()
        delivery_loc = load.locations.filter(location_type='delivery').first()
        loads_with_status.append({
            'load': load,
            'pickup': pickup_loc,
            'delivery': delivery_loc,
            'color': load.color_status,
            'color_label': load.color_label,
            'interest_status': carrier_interests.get(load.pk),  # None / 'pending' / 'accepted' / 'rejected'
            'interest_count': load.interests.count(),
        })

    return render(request, 'load_list.html', {
        'loads': loads_with_status,
        'title': 'Freight Exchange',
        'role': role,
        'unread_count': unread_notification_count(request.user),
    })


@login_required
def add_load(request):
    context = {
        'title': 'Create Freight',
        'body_type_choices': Load.BODY_TYPE_CHOICES,
        'vehicle_size_choices': Load.VEHICLE_SIZE_CHOICES,
        'currency_choices': Load.CURRENCY_CHOICES,
    }
    return render(request, 'add_load.html', context)


@login_required
def save_load(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)

    try:
        data = json.loads(request.body)

        locations_data = data.get('locations', [])
        if len(locations_data) != 2:
            return JsonResponse({'error': 'Exactly 2 locations required.'}, status=400)

        pickup_data = locations_data[0]
        delivery_data = locations_data[1]

        pickup_date_from = parse_datetime(pickup_data.get('date_from', '')) if pickup_data.get('date_from') else None
        delivery_date_from = parse_datetime(delivery_data.get('date_from', '')) if delivery_data.get('date_from') else None

        if not pickup_data.get('country'):
            return JsonResponse({'error': 'Pickup country is required.'}, status=400)
        if not pickup_data.get('city'):
            return JsonResponse({'error': 'Pickup city is required.'}, status=400)
        if not pickup_date_from:
            return JsonResponse({'error': 'Pickup date is required.'}, status=400)
        if not delivery_data.get('country'):
            return JsonResponse({'error': 'Delivery country is required.'}, status=400)
        if not delivery_data.get('city'):
            return JsonResponse({'error': 'Delivery city is required.'}, status=400)
        if not delivery_date_from:
            return JsonResponse({'error': 'Delivery date is required.'}, status=400)

        mileage = None
        if data.get('mileage') not in (None, ''):
            mileage = float(data['mileage'])

        payment_deadline_days = None
        if data.get('payment_deadline_days') not in (None, ''):
            payment_deadline_days = int(data['payment_deadline_days'])

        quantity_raw = data.get('quantity')
        quantity = int(quantity_raw) if quantity_raw not in (None, '') else None

        load = Load(
            created_by=request.user,
            publication_mode=data.get('publication_mode', 'exchange'),
            time_to_submit_offers=parse_datetime(data['time_to_submit_offers']) if data.get('time_to_submit_offers') else None,
            contacts=data.get('contacts', ''),
            buy_now=bool(data.get('buy_now', False)),
            schedule_publication=bool(data.get('schedule_publication', False)),
            scheduled_publish_at=parse_datetime(data['scheduled_publish_at']) if data.get('scheduled_publish_at') else None,
            total_price=data.get('total_price') or None,
            currency=data.get('currency', 'USD'),
            mileage=mileage,
            payment_deadline_days=payment_deadline_days,
            vehicle_size=data.get('vehicle_size', ''),
            body_type=data.get('body_type', ''),
            capacity=data.get('capacity') or None,
            load_meters=data.get('load_meters') or None,
            load_type=data.get('load_type', 'FTL'),
            quantity=quantity,
            stackable=bool(data.get('stackable', False)),
            to_exchange=bool(data.get('to_exchange', False)),
            additional_description=data.get('additional_description', ''),
        )

        try:
            load.full_clean()
        except ValidationError as ve:
            error_messages = []
            for field, errors in ve.message_dict.items():
                for msg in errors:
                    error_messages.append(f"{field}: {msg}" if field != '__all__' else msg)
            return JsonResponse({'error': ' | '.join(error_messages)}, status=400)

        load.save()

        LoadLocation.objects.create(
            load=load, location_type='pickup',
            country=pickup_data.get('country', ''),
            postal_code=pickup_data.get('postal_code', ''),
            city=pickup_data.get('city', ''),
            full_address=pickup_data.get('full_address', ''),
            date_from=pickup_date_from,
            date_to=parse_datetime(pickup_data['date_to']) if pickup_data.get('date_to') else None,
            is_range=bool(pickup_data.get('date_to')) or bool(pickup_data.get('is_range', False)),
        )

        LoadLocation.objects.create(
            load=load, location_type='delivery',
            country=delivery_data.get('country', ''),
            postal_code=delivery_data.get('postal_code', ''),
            city=delivery_data.get('city', ''),
            full_address=delivery_data.get('full_address', ''),
            date_from=delivery_date_from,
            date_to=parse_datetime(delivery_data['date_to']) if delivery_data.get('date_to') else None,
            is_range=bool(delivery_data.get('date_to')) or bool(delivery_data.get('is_range', False)),
        )

        return JsonResponse({'success': True, 'load_id': load.pk, 'redirect': '/load_list/'})

    except ValueError as e:
        return JsonResponse({'error': f'Invalid number: {str(e)}'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def load_detail(request, pk):
    load = get_object_or_404(Load.objects.prefetch_related('locations', 'interests'), pk=pk, is_active=True)

    pickup = load.locations.filter(location_type='pickup').first()
    delivery = load.locations.filter(location_type='delivery').first()
    role = get_user_role(request.user)

    my_interest = None
    interest_status = None
    chat_url = None
    is_owner = load.created_by == request.user

    if role == 'carrier' and not is_owner:
        my_interest = Interest.objects.filter(load=load, carrier=request.user).first()
        if my_interest:
            interest_status = my_interest.status
            if my_interest.status == 'accepted':
                try:
                    chat_url = f'/chat/{my_interest.chat_room.pk}/'
                except ChatRoom.DoesNotExist:
                    chat_url = None

    return render(request, 'load_detail.html', {
        'load': load,
        'pickup': pickup,
        'delivery': delivery,
        'role': role,
        'is_owner': is_owner,
        'interest_status': interest_status,
        'chat_url': chat_url,
        'unread_count': unread_notification_count(request.user),
        'title': f'Load #{pk}',
    })


@login_required
def delete_load(request, pk):
    load = get_object_or_404(Load, pk=pk, created_by=request.user)
    load.is_active = False
    load.save()
    return JsonResponse({'success': True})


@login_required
def load_api_list(request):
    loads = Load.objects.filter(is_active=True).prefetch_related('locations')
    result = []
    for load in loads:
        pickup = load.locations.filter(location_type='pickup').first()
        delivery = load.locations.filter(location_type='delivery').first()
        result.append({
            'id': load.pk,
            'color': load.color_status,
            'color_label': load.color_label,
            'hours_until_pickup': load.hours_until_pickup,
            'load_type': load.load_type,
            'capacity': str(load.capacity) if load.capacity else None,
            'total_price': str(load.total_price) if load.total_price else None,
            'currency': load.currency,
            'mileage': load.mileage,
            'price_per_mile': str(load.price_per_mile) if load.price_per_mile else None,
            'payment_deadline_days': load.payment_deadline_days,
            'body_type': load.body_type,
            'vehicle_size': load.vehicle_size,
            'contacts': load.contacts,
            'buy_now': load.buy_now,
            'pickup': {
                'city': pickup.city if pickup else '',
                'country': pickup.country if pickup else '',
                'postal_code': pickup.postal_code if pickup else '',
                'date_from': pickup.date_from.isoformat() if pickup else None,
            } if pickup else None,
            'delivery': {
                'city': delivery.city if delivery else '',
                'country': delivery.country if delivery else '',
                'postal_code': delivery.postal_code if delivery else '',
                'date_from': delivery.date_from.isoformat() if delivery else None,
            } if delivery else None,
        })
    return JsonResponse({'loads': result})


# ──────────────────────────────────────────────
# Interest views
# ──────────────────────────────────────────────

@login_required
def express_interest(request, load_pk):
    """Carrier expresses interest in a load."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)

    role = get_user_role(request.user)
    if role != 'carrier':
        return JsonResponse({'error': 'Only carriers can express interest.'}, status=403)

    load = get_object_or_404(Load, pk=load_pk, is_active=True)

    if load.created_by == request.user:
        return JsonResponse({'error': 'You cannot express interest in your own load.'}, status=400)

    # Prevent duplicates
    if Interest.objects.filter(load=load, carrier=request.user).exists():
        return JsonResponse({'error': 'You have already expressed interest in this load.'}, status=400)

    try:
        data = json.loads(request.body)
        message = data.get('message', '').strip()[:500]
    except Exception:
        message = ''

    interest = Interest.objects.create(
        load=load,
        carrier=request.user,
        message=message,
        status='pending',
    )

    # Notify the shipper (load publisher)
    if load.created_by:
        pickup = load.locations.filter(location_type='pickup').first()
        delivery = load.locations.filter(location_type='delivery').first()
        route = f"{pickup.country} {pickup.city} → {delivery.country} {delivery.city}" if pickup and delivery else f"Load #{load.pk}"
        Notification.objects.create(
            recipient=load.created_by,
            sender=request.user,
            notification_type='interest',
            interest=interest,
            text=f"{request.user.get_full_name() or request.user.username} is interested in your freight: {route}",
        )

    return JsonResponse({'success': True, 'interest_id': interest.pk, 'status': 'pending'})


@login_required
def interests_page(request):
    """
    Shipper sees all interests on their loads.
    Supports filter by status: ?status=pending / accepted / rejected
    """
    role = get_user_role(request.user)
    if role != 'shipper':
        return redirect('load_list')

    status_filter = request.GET.get('status', 'all')

    # All loads owned by this shipper
    my_loads = Load.objects.filter(created_by=request.user, is_active=True).prefetch_related(
        'locations', 'interests__carrier__user_role', 'interests__carrier__status'
    )

    loads_data = []
    for load in my_loads:
        pickup = load.locations.filter(location_type='pickup').first()
        delivery = load.locations.filter(location_type='delivery').first()

        interests = load.interests.all()
        if status_filter != 'all':
            interests = interests.filter(status=status_filter)

        loads_data.append({
            'load': load,
            'pickup': pickup,
            'delivery': delivery,
            'interests': interests,
            'interest_count': load.interests.count(),
            'pending_count': load.interests.filter(status='pending').count(),
        })

    # Mark notifications as read
    Notification.objects.filter(
        recipient=request.user,
        notification_type='interest',
        is_read=False
    ).update(is_read=True)

    return render(request, 'interests.html', {
        'title': 'My Freight Interests',
        'loads_data': loads_data,
        'status_filter': status_filter,
        'unread_count': unread_notification_count(request.user),
    })


@login_required
def accept_interest(request, interest_pk):
    """Shipper accepts an interest → creates ChatRoom."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)

    role = get_user_role(request.user)
    if role != 'shipper':
        return JsonResponse({'error': 'Shippers only.'}, status=403)

    interest = get_object_or_404(Interest, pk=interest_pk, load__created_by=request.user)

    if interest.status == 'accepted':
        # Already accepted — just redirect to existing chat
        chat_room = ChatRoom.objects.get(interest=interest)
        return JsonResponse({'success': True, 'chat_url': f'/chat/{chat_room.pk}/'})

    interest.status = 'accepted'
    interest.save()

    # Create chat room
    chat_room = ChatRoom.objects.create(
        interest=interest,
        shipper=request.user,
        carrier=interest.carrier,
    )

    # Notify carrier
    Notification.objects.create(
        recipient=interest.carrier,
        sender=request.user,
        notification_type='accepted',
        interest=interest,
        text=f"{request.user.get_full_name() or request.user.username} accepted your interest. Chat is now open!",
    )

    return JsonResponse({'success': True, 'chat_url': f'/chat/{chat_room.pk}/'})


@login_required
def reject_interest(request, interest_pk):
    """Shipper rejects an interest."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)

    role = get_user_role(request.user)
    if role != 'shipper':
        return JsonResponse({'error': 'Shippers only.'}, status=403)

    interest = get_object_or_404(Interest, pk=interest_pk, load__created_by=request.user)
    interest.status = 'rejected'
    interest.save()

    # Notify carrier
    Notification.objects.create(
        recipient=interest.carrier,
        sender=request.user,
        notification_type='rejected',
        interest=interest,
        text=f"{request.user.get_full_name() or request.user.username} rejected your interest.",
    )

    return JsonResponse({'success': True})


# ──────────────────────────────────────────────
# Notifications
# ──────────────────────────────────────────────

@login_required
def notifications_api(request):
    """Return unread notifications as JSON (for bell icon polling)."""
    notifs = Notification.objects.filter(recipient=request.user).order_by('-created_at')[:30]
    data = []
    for n in notifs:
        data.append({
            'id': n.pk,
            'type': n.notification_type,
            'text': n.text,
            'is_read': n.is_read,
            'created_at': n.created_at.isoformat(),
            'chat_url': f'/chat/{n.interest.chat_room.pk}/' if (
                n.notification_type == 'accepted' and
                hasattr(n.interest, 'chat_room')
            ) else None,
            'interests_url': '/interests/' if n.notification_type == 'interest' else None,
        })
    return JsonResponse({'notifications': data, 'unread_count': unread_notification_count(request.user)})


@login_required
def mark_notifications_read(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'success': True})


# ──────────────────────────────────────────────
# Chat views
# ──────────────────────────────────────────────

@login_required
def chat_view(request, room_pk):
    """Main chat page."""
    room = get_object_or_404(ChatRoom, pk=room_pk)

    # Only shipper or carrier of this room can access
    if request.user not in (room.shipper, room.carrier):
        return redirect('load_list')

    messages = room.messages.select_related('sender').all()

    # Mark messages as read
    room.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)

    # Determine the "other" user
    other_user = room.carrier if request.user == room.shipper else room.shipper

    return render(request, 'chat.html', {
        'title': f'Chat — Load #{room.interest.load.pk}',
        'room': room,
        'messages': messages,
        'other_user': other_user,
        'load': room.interest.load,
        'unread_count': unread_notification_count(request.user),
    })


@login_required
def send_message(request, room_pk):
    """Send a chat message (AJAX POST)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)

    room = get_object_or_404(ChatRoom, pk=room_pk)
    if request.user not in (room.shipper, room.carrier):
        return JsonResponse({'error': 'Access denied.'}, status=403)

    try:
        data = json.loads(request.body)
        text = data.get('text', '').strip()
    except Exception:
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)

    if not text:
        return JsonResponse({'error': 'Message cannot be empty.'}, status=400)

    msg = ChatMessage.objects.create(room=room, sender=request.user, text=text)

    # Notify the other user
    other = room.carrier if request.user == room.shipper else room.shipper
    Notification.objects.create(
        recipient=other,
        sender=request.user,
        notification_type='message',
        text=f"New message from {request.user.get_full_name() or request.user.username}",
    )

    return JsonResponse({
        'success': True,
        'message': {
            'id': msg.pk,
            'text': msg.text,
            'sender': request.user.get_full_name() or request.user.username,
            'sender_id': request.user.pk,
            'created_at': msg.created_at.strftime('%H:%M'),
        }
    })


@login_required
def poll_messages(request, room_pk):
    """Long-poll for new messages after a given message id."""
    room = get_object_or_404(ChatRoom, pk=room_pk)
    if request.user not in (room.shipper, room.carrier):
        return JsonResponse({'error': 'Access denied.'}, status=403)

    after_id = int(request.GET.get('after', 0))
    msgs = room.messages.filter(pk__gt=after_id).select_related('sender')

    # Mark as read
    msgs.exclude(sender=request.user).update(is_read=True)

    data = [{
        'id': m.pk,
        'text': m.text,
        'sender': m.sender.get_full_name() or m.sender.username,
        'sender_id': m.sender.pk,
        'created_at': m.created_at.strftime('%H:%M'),
        'is_mine': m.sender == request.user,
    } for m in msgs]

    return JsonResponse({'messages': data})


@login_required
def my_chats(request):
    """List all chat rooms for current user."""
    rooms = ChatRoom.objects.filter(
        Q(shipper=request.user) | Q(carrier=request.user)
    ).select_related('interest__load', 'shipper', 'carrier').prefetch_related('messages')

    rooms_data = []
    for room in rooms:
        last_msg = room.messages.last()
        unread = room.messages.filter(is_read=False).exclude(sender=request.user).count()
        other = room.carrier if request.user == room.shipper else room.shipper
        pickup = room.interest.load.locations.filter(location_type='pickup').first()
        delivery = room.interest.load.locations.filter(location_type='delivery').first()
        rooms_data.append({
            'room': room,
            'other_user': other,
            'last_message': last_msg,
            'unread_count': unread,
            'load': room.interest.load,
            'pickup': pickup,
            'delivery': delivery,
        })

    return render(request, 'my_chats.html', {
        'title': 'My Chats',
        'rooms_data': rooms_data,
        'unread_count': unread_notification_count(request.user),
    })


@login_required
def carrier_info(request, carrier_pk):
    """
    Public carrier profile page.
    Accessible by shippers (e.g. from the interests page).
    Shows real name/username from DB; all stats generated in JS using carrier.pk as seed.
    """
    carrier = get_object_or_404(User, pk=carrier_pk)

    # Ensure this user is actually a carrier
    role = get_user_role(carrier)
    if role != 'carrier':
        return redirect('load_list')

    # Get the DB status score (defaults to 50 if not set)
    try:
        carrier_status = carrier.status.score
    except Exception:
        carrier_status = 50

    return render(request, 'carrier_info.html', {
        'title': f'{carrier.get_full_name()} — Tashuvchi profili',
        'carrier': carrier,
        'carrier_status': carrier_status,
    })