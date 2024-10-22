import json, secrets

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from call.models import AbonentPair, CallLineStatus


class IndexView(TemplateView):
    template_name = 'call/index.html'


@csrf_exempt
def callLineProcess(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        code = data.get('code')

        AbonentPair.cleanOldRecords()

        if code == 'dial':
            return processDial(data.get('call_code'))

        user_id = data.get('user_id')
        pair = AbonentPair.getPairByUserId(user_id)
        if pair is None or (pair.initiator_user_id != user_id and pair.subscriber_user_id != user_id):
            return HttpResponse('Не найден user_id', status=400)

        if code == 'disconnect':
            # для упрощения: если кто-то из пары отключается, то удаляем обоих.
            pair.delete()
            return HttpResponse(status=200)

        pair.updateLastRequestTime(user_id)

        if code == 'get_status':
            return processGetStatus(pair, user_id)
        elif code == 'offer':
            return processOffer(pair, user_id, data.get('offer'))
        elif code == 'answer':
            return processAnswer(pair, user_id, data.get('answer'))
        elif code == 'ice':
            return processIce(pair, user_id, data.get('ice'))

    return HttpResponse('Неверное поле code', status=400)


def processDial(call_code):
    ok = False

    pair = AbonentPair.getFreePairByCallCode(call_code)
    user_id = secrets.token_hex(32)

    if pair is None:
        pair = AbonentPair()
        pair.call_code = call_code
        pair.initiator_user_id = user_id
        pair.save()
        ok = True
    else:
        pair.status = CallLineStatus.NeedInit
        pair.subscriber_user_id = user_id
        pair.save()
        ok = True

    if ok:
        return HttpResponse(json.dumps({'user_id': user_id}), status=200)

    return HttpResponse(status=400)


def processGetStatus(pair, user_id):
    if pair.status == CallLineStatus.WaitForResponse:
        return HttpResponse(json.dumps({}), status=200)

    if pair.status == CallLineStatus.NeedInit and pair.initiator_user_id == user_id and pair.initiator_offer == '':
        return HttpResponse(
            json.dumps({
                'code': str(CallLineStatus.NeedInit)
            }), status=200)

    if pair.status == CallLineStatus.Offered and pair.subscriber_user_id == user_id:
        return HttpResponse(
            json.dumps({
                'code': str(CallLineStatus.Offered),
                'offer': json.loads(pair.initiator_offer)
            }), status=200)

    if pair.status == CallLineStatus.Answered and pair.initiator_user_id == user_id:
        pair.status = CallLineStatus.Connected  # остаётся только обменяться ice-маршрутами
        pair.save()

        return HttpResponse(
            json.dumps({
                'code': str(CallLineStatus.Answered),
                'answer': json.loads(pair.subscriber_answer)
            }), status=200)

    if pair.status == CallLineStatus.Connected:
        new_ice_routes = json.loads(pair.subscriber_new_ice_routes if (pair.initiator_user_id == user_id) else pair.initiator_new_ice_routes)

        if len(new_ice_routes) > 0:
            if pair.initiator_user_id == user_id:
                pair.subscriber_new_ice_routes = json.dumps([])
            else:
                pair.initiator_new_ice_routes = json.dumps([])
            pair.save()

        return HttpResponse(
            json.dumps({
                'code': str(CallLineStatus.Connected),
                'new_ice_routes': new_ice_routes
            }), status=200)

    return HttpResponse(json.dumps({}), status=200)


def processOffer(pair, user_id, json_offer):
    if pair.status != CallLineStatus.NeedInit or pair.initiator_user_id != user_id:
        return HttpResponse(status=400)

    pair.status = CallLineStatus.Offered
    pair.initiator_offer = json.dumps(json_offer)
    pair.save()
    return HttpResponse(status=200)


def processAnswer(pair, user_id, json_answer):
    if pair.status != CallLineStatus.Offered or pair.subscriber_user_id != user_id:
        return HttpResponse(status=400)

    pair.status = CallLineStatus.Answered
    pair.subscriber_answer = json.dumps(json_answer)
    pair.save()
    return HttpResponse(status=200)


def processIce(pair, user_id, json_ice):
    if pair.initiator_user_id == user_id:
        json_ice_routes = json.loads(pair.initiator_new_ice_routes)
        json_ice_routes.append(json_ice)
        pair.initiator_new_ice_routes = json.dumps(json_ice_routes)
        pair.save()
    else:
        json_ice_routes = json.loads(pair.subscriber_new_ice_routes)
        json_ice_routes.append(json_ice)
        pair.subscriber_new_ice_routes = json.dumps(json_ice_routes)
        pair.save()

    return HttpResponse(status=200)
