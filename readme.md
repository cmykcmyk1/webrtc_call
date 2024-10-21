## Звонок по WebRTC

<!-- <details>
<summary>Русский</summary>
<br/> -->

<details>
<summary>Короткий конспект по WebRTC</summary>
<br/>

WebRTC - технология, которая позволяет транслировать аудио-видео между клиентами напрямую без сервера.  
В современных браузерах уже имеется по умолчанию WebRTC API.  
  
`RTCPeerConnection` - интерфейс для создания WebRTC-соединения.  
Каждому клиенту нужно создать по экземпляру данного интерфейса и должным образом проинициализировать:
```
const rtc_peer = new RTCPeerConnection({
    iceServers: [
        {
            urls: ['stun:stun1.l.google.com:19302', 'stun:stun3.l.google.com:19302']  // чтобы клиенты смогли подключиться по интернету (см.п.2)
        }
    ]
});

```
<br/>

<details>
<summary>1. Добавление медиатреков и создание RTCDataChannel</summary>
<br/>

Метод `addTrack(track)` позволяет добавлять медиатреки для их передачи по соединению.  
Получим треки текущей веб-камеры и микрофона, и добавим их в RTC-соединение:
```
const stream = await navigator.mediaDevices.getUserMedia({video: true, audio: true});
stream.getTracks().forEach(track => rtc_peer.addTrack(track));

```

На каждый добавленный трек у принимающей стороны будет вызван обратный вызов `ontrack(event)`:
```
const remote_stream = new MediaStream();
// remote_stream требуется куда-нибудь установить для воспроизведения. Можно в объекты <audio>, <video>.
// video_object.srcObject = remote_stream;

rtc_peer.ontrack = event => {
    remote_stream.addTrack(event.track);
}

```

Помимо медиаданных, по RTC можно передавать произвольные данные по каналу данных `RTCDataChannel`.  

Нам для созвона это может пригодится для передачи каких-то специальных сообщений:  
 - для завершения разговора;
 - сообщения, что абонент отключил/включил камеру/микрофон.
  
```
let datachannel = null;

```

Одна сторона использует метод `createDataChannel(str_channel_label)`:
```
datachannel = rtc_peer.createDataChannel('special_datachannel');
datachannel.onmessage = event => {
    // processDataChannel(JSON.parse(event.data));
}

```

Вторая сторона получает обратный вызов `ondatachannel(event)`:
```
rtc_peer.ondatachannel = event => {
    if (event.channel.label === 'special_datachannel') {
        datachannel = event.channel;
        datachannel.onmessage = event => {
            // processDataChannel(JSON.parse(event.data));
        }
    }
}

```

Для отправки сообщений по каналу данных используется метод `send(str)`:
```
datachannel.send(JSON.stringify({
    code: 'reject'
}));

datachannel.send(JSON.stringify({
    code: 'mute_microphone',
    value: true
}));

```

Переданные сообщения будут получены обратным вызовом `onmessage(event)`.  

</details>

<details>
<summary>2. Задание onicecandidate</summary>
<br/>

Требуется установить обратный вызов `onicecandidate(event)`, который будет вызываться во время выполнения пункта 3.  

`RTCIceCandidate` - возможный маршрут, по которому RTC-соединение сможет подключиться к удалённому клиенту.  
Внутри этого объекта имеется информация об IP клиента. И таких кандидатов может быть несколько.  
Какие-то будут с локальным IP (`192.168.1.*`), какие-то с внешним (`85.*.*.*`).  

Как раз для получения внешнего IP, мы и прописали STUN-сервера, чтобы они определяли нас.  

```
rtc_peer.onicecandidate = event => {
    const ice_route = event.candidate;
    
    // storing ice_route or sending it right now ...
};

```

Решайте сами когда отправлять ICE-маршруты: сразу внутри обратного вызова или после формирования оффера/ответа (п.3).  

В этом проекте я каждого кандидата отправляю сразу на сервер, там они копятся в отдельный для каждого абонента массив, и на последнем этапе, после обмена оффера/ответа, разом все сразу отправляются собеседнику.  

</details>

<details>
<summary>3. Создание оффера и ответа</summary>
<br/>

Теперь каждой стороне требуется создать описание их передающихся данных и каким-то образом передать это описание друг другу.  
По этому описанию будут сформированны удалённые треки.  

`RTCSessionDescription` - описание сессии. Объект из двух полей:
```
{
    type: 'offer',  // or 'answer'
    sdp: '...'      // description AV-codecs and etc...
}

```

Одна сторона создаёт оффер с описанием своего потока, используя метод `createOffer(...)`, и передаёт собеседнику:
```
const offer = await rtc_peer.createOffer({  // можно вызывать без аргументов
    offerToReceiveAudio: true,  // если инициатор передаёт только аудио, то по умолчанию и у отвечающего будет сформирован ответ только аудио.
    offerToReceiveVideo: true   // с этими параметрами будет приниматься и видео, и аудио, при их наличии.
});
await rtc_peer.setLocalDescription(offer);

// sending offer ...

```

Вторая сторона формирует ответ, используя `createAnswer()`, и передаёт первой:
```
await rtc_peer.setRemoteDescription(offer_from_initiator);

const answer = await rtc_peer.createAnswer();
await rtc_peer.setLocalDescription(answer);

// sending answer ...

```

```
// initiator
await rtc_peer.setRemoteDescription(answer_from_subscriber);

```

</details>

<details>
<summary>4. Добавление ICE-кандидатов</summary>
<br/>

Осталось в RTC-соединения добавить сформированные ICE-маршруты вашего собеседника:
```
// receiving ice_routes_from_subscriber ...

ice_routes_from_subscriber.forEach(route => rtc_peer.addIceCandidate(route));

```

И, о чудо, оно заработает)  

</details>
<br/>

Таким образом, для трансляции аудио-видео по WebRTC двум клиентам нужно обменяться оффером/ответом, и ICE-кандидатами, и передача будет установлена напрямую без участия сервера.  
Надо только придумать, как провести этот обмен.  
Для этого и сделан этот проект)  
  
</details>

---
<br/>

Простой созвон двух абонентов на POST-запросах:
 - Клиенты отправляют свои данные серверу
 - Cервер ретранслирует собеседнику
 - Клиенты устанавливают WebRTC-соединение и сервер забывает об абонентах

### Запуск проекта

1. Установите в своё окружение Django.  
  
2. В `webrtc_call/settings.py` отредактируйте `ALLOW_HOSTS`, дополните свой сетевой адрес:
```
ALLOWED_HOSTS = ['127.0.0.1', '192.168.1.1']

```

3. В терминале выполните:
```
// Django is installed ...

python manage.py makemigrations
python manage.py makemigrations video_call
python manage.py migrate

python manage.py test
python manage.py runserver 0.0.0.0:8000

```

4. В браузере открываем `http://ip_addr:8000/video_call`, убеждаемся, что сайт открывается.  
Скорее всего, браузер не даст работать с вашими медиаустройствами без https.  
Требуется добавить адрес `http://ip_addr:8000/` в исключения вашего браузера.  
https://stackoverflow.com/questions/40696280/unsafely-treat-insecure-origin-as-secure-flag-is-not-working-on-chrome  

Откройте две вкладки на компьютере или откройте сайт со смартфона по домашнему Wi-Fi.  
Вперёд звонить самому себе)  

<!-- </details> -->

---
