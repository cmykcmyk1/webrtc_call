import json
import datetime

from enum import IntEnum
from django.db import models
from django.db.models import Q
from django.utils import timezone


class CallLineStatus(IntEnum):
    WaitForResponse = 0
    NeedInit = 1
    Offered = 2
    Answered = 3
    Connected = 4

    def __str__(self):
        if self == CallLineStatus.WaitForResponse:
            return 'wait_for_response'
        if self == CallLineStatus.NeedInit:
            return 'need_init'
        if self == CallLineStatus.Offered:
            return 'offered'
        if self == CallLineStatus.Answered:
            return 'answered'
        if self == CallLineStatus.Connected:
            return 'connected'


class AbonentPair(models.Model):
    call_code = models.CharField(max_length=255)

    status = models.IntegerField(default=CallLineStatus.WaitForResponse)

    initiator_user_id = models.CharField(max_length=64)
    initiator_offer = models.TextField(blank=True)
    initiator_new_ice_routes = models.TextField(default=json.dumps([]), blank=True)
    initiator_last_request_time = models.DateTimeField(default=timezone.now)

    subscriber_user_id = models.CharField(max_length=64)
    subscriber_answer = models.TextField(blank=True)
    subscriber_new_ice_routes = models.TextField(default=json.dumps([]), blank=True)
    subscriber_last_request_time = models.DateTimeField(default=timezone.now)

    def getFreePairByCallCode(call_code):
        try:
            return AbonentPair.objects.get(Q(call_code=call_code) & Q(subscriber_user_id=''))
        except AbonentPair.DoesNotExist:
            return None

    def getPairByUserId(user_id):
        try:
            return AbonentPair.objects.get(Q(initiator_user_id=user_id) | Q(subscriber_user_id=user_id))
        except AbonentPair.DoesNotExist:
            return None

    def updateLastRequestTime(self, user_id):
        if self.initiator_user_id == user_id:
            self.initiator_last_request_time = timezone.now()

            if self.subscriber_user_id == '':
                self.subscriber_last_request_time = timezone.now()
        else:
            self.subscriber_last_request_time = timezone.now()
        self.save()

    def cleanOldRecords():
        AbonentPair.objects.filter(
            Q(initiator_last_request_time__lt =timezone.now() - datetime.timedelta(seconds=10)) |
            Q(subscriber_last_request_time__lt=timezone.now() - datetime.timedelta(seconds=10))
        ).delete()
