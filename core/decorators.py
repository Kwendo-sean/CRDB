from functools import wraps
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from .models import Participant


def resolve_participant(request):
    """Return the Learning Pass holder for this session, or None.

    A session cookie can outlive the row it points at (database restore, participant
    deactivated, hand-edited cookie), so an unusable value must read as "signed out"
    rather than raising.
    """
    raw = request.session.get("participant_id")
    if not raw:
        return None
    try:
        return Participant.objects.filter(pk=raw, is_active=True).first()
    except (ValidationError, ValueError, TypeError):
        return None


def participant_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        participant = resolve_participant(request)
        if participant is None:
            request.session.pop("participant_id", None)
            return redirect("participant-access")
        request.participant = participant
        return view(request, *args, **kwargs)

    return wrapped
