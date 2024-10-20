import json
from time import sleep

from django.core.handlers.wsgi import WSGIRequest
from django.test import TestCase

from video_call.models import AbonentPair, CallLineStatus
import video_call.views as views


class VideoCallTests(TestCase):
    def do_dial(self, call_code) -> str:
        response = views.processDial(call_code)
        self.assertEqual(response.status_code, 200)

        user_id = json.loads(response.content).get('user_id')
        print('Добавили', user_id)
        return user_id

    def do_init(self, user_id):
        pair = AbonentPair.getPairByUserId(user_id)
        self.assertEqual(pair.status, CallLineStatus.NeedInit)

        response = views.processGetStatus(pair, user_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content).get('code'), str(CallLineStatus.NeedInit))

        response = views.processOffer(pair, user_id, {'type': 'offer', 'description': 'stream_description'})
        self.assertEqual(response.status_code, 200)

        pair = AbonentPair.getPairByUserId(user_id)
        self.assertEqual(pair.status, CallLineStatus.Offered)

    def load_offer(self, user_id):
        pair = AbonentPair.getPairByUserId(user_id)
        self.assertEqual(pair.status, CallLineStatus.Offered)

        response = views.processGetStatus(pair, user_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content).get('code'), str(CallLineStatus.Offered))

        print(user_id, 'получил оффер', json.loads(response.content).get('offer'))

        response = views.processAnswer(pair, user_id, {'type': 'answer', 'description': 'stream_description'})
        self.assertEqual(response.status_code, 200)

        pair = AbonentPair.getPairByUserId(user_id)
        self.assertEqual(pair.status, CallLineStatus.Answered)

    def load_answer(self, user_id):
        pair = AbonentPair.getPairByUserId(user_id)
        self.assertEqual(pair.status, CallLineStatus.Answered)

        response = views.processGetStatus(pair, user_id)
        self.assertEqual(response.status_code, 200)

        json_data = json.loads(response.content)
        self.assertEqual(json_data.get('code'), str(CallLineStatus.Answered))

        print(user_id, 'получил ответ', json_data.get('answer'))

        pair = AbonentPair.getPairByUserId(user_id)
        self.assertEqual(pair.status, CallLineStatus.Connected)

    def send_ice(self, user_id, ice_route):
        pair = AbonentPair.getPairByUserId(user_id)
        response = views.processIce(pair, user_id, ice_route)
        self.assertEqual(response.status_code, 200)

        print(user_id, 'отправил ice-маршрут', json.dumps(ice_route))

    def load_ice_routes(self, user_id):
        pair = AbonentPair.getPairByUserId(user_id)
        self.assertEqual(pair.status, CallLineStatus.Connected)

        response = views.processGetStatus(pair, user_id)
        self.assertEqual(response.status_code, 200)

        json_data = json.loads(response.content)
        self.assertEqual(json_data.get('code'), str(CallLineStatus.Connected))

        new_ice_routes = json_data.get('new_ice_routes')

        print(user_id, 'получил ice-маршруты', json.dumps(new_ice_routes))

    def test_simple_call(self):
        print('Простой созвон двух абонентов')

        self.assertEqual(AbonentPair.objects.count(), 0)

        user_id_1 = self.do_dial('testcall111')
        self.assertEqual(AbonentPair.objects.count(), 1)

        pair = AbonentPair.getPairByUserId(user_id_1)
        response = views.processGetStatus(pair, user_id_1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(pair.status, CallLineStatus.WaitForResponse)

        user_id_2 = self.do_dial('testcall111')
        self.assertEqual(AbonentPair.objects.count(), 1)

        self.do_init(user_id_1)
        self.load_offer(user_id_2)
        self.load_answer(user_id_1)

        self.send_ice(user_id_1, {'type': 'ice', 'address': 'localhost:8001'})
        self.send_ice(user_id_1, {'type': 'ice', 'address': 'localhost:8002'})
        self.send_ice(user_id_1, {'type': 'ice', 'address': 'remotehost:8001'})

        self.send_ice(user_id_2, {'type': 'ice', 'address': '192.168.1.1:27015'})
        self.send_ice(user_id_2, {'type': 'ice', 'address': '192.168.1.1:27016'})
        self.send_ice(user_id_2, {'type': 'ice', 'address': '192.168.1.1:27017'})

        self.load_ice_routes(user_id_1)
        self.load_ice_routes(user_id_2)

        self.load_ice_routes(user_id_1)
        self.load_ice_routes(user_id_2)

        print('Уснул на 10 секунд')
        sleep(10.1)

        AbonentPair.cleanOldRecords()
        self.assertEqual(AbonentPair.objects.count(), 0)


    def test_5_abonents_call(self):
        print('5 абонентов звонят по одинаковому коду')

        self.assertEqual(AbonentPair.objects.count(), 0)

        user_id_1 = self.do_dial('testcall2')
        self.assertEqual(AbonentPair.objects.count(), 1)

        user_id_2 = self.do_dial('testcall2')
        self.assertEqual(AbonentPair.objects.count(), 1)

        user_id_3 = self.do_dial('testcall2')
        self.assertEqual(AbonentPair.objects.count(), 2)

        user_id_4 = self.do_dial('testcall2')
        self.assertEqual(AbonentPair.objects.count(), 2)

        user_id_5 = self.do_dial('testcall2')
        self.assertEqual(AbonentPair.objects.count(), 3)

        pair_1 = AbonentPair.getPairByUserId(user_id_1)
        self.assertEqual(pair_1.subscriber_user_id, user_id_2)

        pair_2 = AbonentPair.getPairByUserId(user_id_3)
        self.assertEqual(pair_2.subscriber_user_id, user_id_4)

        pair_3 = AbonentPair.getPairByUserId(user_id_5)
        self.assertEqual(pair_3.subscriber_user_id, '')

        self.do_init(user_id_1)
        self.do_init(user_id_3)

        self.load_offer(user_id_2)
        self.load_offer(user_id_4)

        self.load_answer(user_id_1)
        self.load_answer(user_id_3)

        self.send_ice(user_id_1, {'type': 'ice', 'address': '192.168.1.1:27015'})
        self.send_ice(user_id_2, {'type': 'ice', 'address': '192.168.1.2:27015'})
        self.send_ice(user_id_3, {'type': 'ice', 'address': '192.168.1.3:27015'})
        self.send_ice(user_id_4, {'type': 'ice', 'address': '192.168.1.4:27015'})
        self.send_ice(user_id_5, {'type': 'ice', 'address': '192.168.1.5:27015'})

        self.load_ice_routes(user_id_1)
        self.load_ice_routes(user_id_2)
        self.load_ice_routes(user_id_3)
        self.load_ice_routes(user_id_4)

        print('Уснул на 5 секунд')
        sleep(5.1)
        AbonentPair.cleanOldRecords()
        self.assertEqual(AbonentPair.objects.count(), 3)

        pair_3 = AbonentPair.getPairByUserId(user_id_5)
        pair_3.updateLastRequestTime(user_id_5)

        print('Уснул ещё на 5 секунд')
        sleep(5.1)
        AbonentPair.cleanOldRecords()
        self.assertEqual(AbonentPair.objects.count(), 1)

        pair_3 = AbonentPair.getPairByUserId(user_id_5)
        response = views.processGetStatus(pair_3, user_id_5)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(pair_3.status, CallLineStatus.WaitForResponse)
