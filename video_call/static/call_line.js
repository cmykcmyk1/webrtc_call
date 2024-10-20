const CENTRAL_SERVER_URL = window.location.href + 'call_line_process/';

async function checkAndRequestPermissions() {
     return new Promise((resolve, reject) => {
         function stopTracks(stream) {
             stream.getTracks().forEach(track => track.stop());
         }

         navigator.mediaDevices.getUserMedia({video: true, audio: true})
             .then(stream => {
                 stopTracks(stream);
                 resolve();
             })
             .catch(err => {
                 console.error('Нет доступа к камере:', err)

                 // может хотя бы только микрофон

                 navigator.mediaDevices.getUserMedia({audio: true})
                     .then(stream => {
                         stopTracks(stream);
                         resolve();
                     })
                     .catch(err => {
                         console.error('Нет доступа к микрофону:', err);
                         reject();
                     });
             });
     });
}

class CallLine {
    static Status = {};

    constructor() {
        this._cur_status = CallLine.Status.Idle;
        this._on_status_changed = [];
        this._on_connected = [];
        this._on_rejected = [];

        this._user_id = '';

        this._rtc_peer = null;
        this._remote_stream = null;
        this._video_object = null;

        this._system_code_datachannel = null;
        this._on_mute_updated = [];

        this._get_status_timer_id = -1;
    }

    addOnStatusChanged(f) {
        this._on_status_changed.push(f);
    }

    addOnConnected(f) {
        this._on_connected.push(f);
    }

    addOnRejected(f) {
        this._on_rejected.push(f);
    }

    addOnMuteUpdated(f) {
        this._on_mute_updated.push(f);
    }

    setupRemoteStreamOutput(video_object) {
        this._video_object = video_object;
    }

    currentStatus() {
        return this._cur_status;
    }

    setCameraMuted(enabled) {
        this._setTrackMuted(enabled, 'video')
    }

    isCameraMuted() {
        return this._isTrackMuted('video');
    }

    setMicrophoneMuted(enabled) {
        this._setTrackMuted(enabled, 'audio')
    }

    isMicrophoneMuted() {
        return this._isTrackMuted('audio');
    }

    _setTrackMuted(enabled, kind) {
        if (this._cur_status !== CallLine.Status.Call)
            return;

        this._rtc_peer.getSenders().forEach(sender => {
            if (sender.track && sender.track.kind === kind) {
                sender.track.enabled = !enabled;
            }
        });

        this._on_mute_updated.forEach(callback => callback());

        this._system_code_datachannel.send(JSON.stringify({
            code: `mute_${kind}`,
            value: enabled
        }));
    }

    _isTrackMuted(kind) {
        if (this._cur_status !== CallLine.Status.Call)
            return false;

        const sender = this._rtc_peer.getSenders().find(sender => sender.track && sender.track.kind === kind);
        if (sender)
            return !sender.track.enabled;

        return true;
    }

    setAudioOutputMuted(enabled) {
        if (this._cur_status !== CallLine.Status.Call)
            return;

        this._video_object.muted = enabled;
        this._on_mute_updated.forEach(callback => callback());
    }

    isAudioOutputMuted() {
        if (this._cur_status !== CallLine.Status.Call)
            return false;

        return this._video_object.muted;
    }

    isSubscriberCameraMuted() {
        return this._isSubscriberTrackMuted('video');
    }

    isSubscriberMicrophoneMuted() {
        return this._isSubscriberTrackMuted('audio');
    }

    _isSubscriberTrackMuted(kind) {
        if (this._cur_status !== CallLine.Status.Call)
            return false;

        const remote_track = this._video_object.srcObject.getTracks().find(track => track.kind === kind);
        if (remote_track)
            return !remote_track.enabled;

        return true;
    }

    async dial(call_code) {
        if (this._cur_status !== CallLine.Status.Idle || call_code === '')
            return;

        console.assert(this._rtc_peer == null);

        const dial_response = await fetch(CENTRAL_SERVER_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                code: 'dial',
                call_code: call_code
            })
        });

        if (dial_response.status === 200) {
            const json_data = await dial_response.json();
            this._user_id = json_data.user_id;

            console.log('Dial: success\n', 'user_id:', this._user_id);
        } else {
            console.error('Dial: error');
            return;
        }

        this._rtc_peer = new RTCPeerConnection({
            iceServers: [
                {
                    urls: ['stun:stun1.l.google.com:19302', 'stun:stun3.l.google.com:19302']
                }
            ]
        });

        try {
            const stream = await navigator.mediaDevices.getUserMedia({video: true});
            stream.getTracks().forEach(track => this._rtc_peer.addTrack(track));
        }
        catch (err) {
            console.warn('Dial: error loading video device', err);
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({audio: true});
            stream.getTracks().forEach(track => this._rtc_peer.addTrack(track));
        }
        catch (err) {
            console.warn('Dial: error loading audio device', err);
        }

        this._rtc_peer.onicecandidate = async event => {
            if (event.candidate) {
                const response = await fetch(CENTRAL_SERVER_URL, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        code: 'ice',
                        user_id: this._user_id,
                        ice: event.candidate
                    })
                });

                if (response.status === 200) {
                    console.log('Sent ICE:\n', event.candidate);
                } else {
                    console.error('Sent ICE: error');
                }
            }
        };

        this._rtc_peer.onconnectionstatechange = event => {
            if (this._rtc_peer.connectionState === 'connected') {
                this._onSuccessfulConnection();
            }
            else if (this._rtc_peer.connectionState === 'failed' ||
                     this._rtc_peer.connectionState === 'disconnected' ||
                     this._rtc_peer.connectionState === 'closed') {
                this._resetCallLine();
            }
        };

        this._remote_stream = new MediaStream();
        this._video_object.srcObject = this._remote_stream;

        this._rtc_peer.ontrack = event => {
            if (event.track) {
                this._remote_stream.addTrack(event.track);
                console.log('Add remote track:\n', event.track);
            }
        }

        this._rtc_peer.ondatachannel = event => {
            console.log('Got Datachannel:\n', event);

            if (event.channel.label === 'system_code') {
                this._system_code_datachannel = event.channel;
                this._system_code_datachannel.onmessage = event => this._processSystemDataChannel(JSON.parse(event.data));
            }
        }

        this._get_status_timer_id = setInterval(() => this._getStatusFromServer(), 3000);

        this._cur_status = CallLine.Status.WaitForResponse;
        this._on_status_changed.forEach(callback => callback());
    }

    async reject() {
        if (this._cur_status === CallLine.Status.Call) {
            this._system_code_datachannel.send(JSON.stringify({
                code: 'reject'
            }));
        } else {
            await fetch(CENTRAL_SERVER_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    code: 'disconnect',
                    user_id: this._user_id
                })
            });
        }

        this._resetCallLine();
    }

    _resetCallLine() {
        this._user_id = '';

        this._video_object.srcObject = null;

        if (this._remote_stream) {
            this._remote_stream.getTracks().forEach(track => {
                track.stop();
                this._remote_stream.removeTrack(track);
            });
            this._remote_stream = null;
        }

        if (this._system_code_datachannel) {
            this._system_code_datachannel.close();
            this._system_code_datachannel = null;
        }

        if (this._rtc_peer) {
            this._rtc_peer.getReceivers().forEach(recv => recv.track.stop());
            this._rtc_peer.getSenders().forEach(sender => {
                if (sender.track) {
                    sender.track.stop();
                }

                this._rtc_peer.removeTrack(sender);
            });

            this._rtc_peer.close();
            this._rtc_peer = null;
        }

        if (this._get_status_timer_id !== -1) {
            clearInterval(this._get_status_timer_id);
            this._get_status_timer_id = -1;
        }

        this._cur_status = CallLine.Status.Idle;
        this._on_status_changed.forEach(callback => callback());
        this._on_rejected.forEach(callback => callback());
    }

    async _getStatusFromServer() {
        const response = await fetch(CENTRAL_SERVER_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                code: 'get_status',
                user_id: this._user_id
            })
        });

        if (response.status !== 200) {
            this._resetCallLine();
            return;
        }

        const json_data = await response.json();
        const code = json_data.code;

        if (code === 'need_init') {
            await this._processNeedInit();
        } else if (code === 'offered') {
            await this._processOffer(json_data.offer)
        } else if (code === 'answered') {
            await this._processAnswer(json_data.answer)
        } else if (code === 'connected') {
            if (json_data.new_ice_routes.length > 0) {
                this._processIce(json_data.new_ice_routes);
            }
        }
    }

    async _processNeedInit() {
        console.log('Require initialization');

        console.assert(this._rtc_peer != null);

        this._system_code_datachannel = this._rtc_peer.createDataChannel('system_code');
        this._system_code_datachannel.onmessage = event => this._processSystemDataChannel(JSON.parse(event.data));

        const offer = await this._rtc_peer.createOffer({
            offerToReceiveAudio: true,
            offerToReceiveVideo: true
        });
        await this._rtc_peer.setLocalDescription(offer);

        const response = await fetch(CENTRAL_SERVER_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                code: 'offer',
                user_id: this._user_id,
                offer: offer
            })
        });

        if (response.status === 200) {
            console.log('Sent Offer:\n', offer);
        } else {
            console.error('Sent Offer: error');
        }

        this._cur_status = CallLine.Status.Connecting;
        this._on_status_changed.forEach(callback => callback());
    }

    async _processOffer(json_offer) {
        console.log('Got Offer:\n', json_offer);

        console.assert(this._rtc_peer != null);

        await this._rtc_peer.setRemoteDescription(json_offer);

        const answer = await this._rtc_peer.createAnswer();
        await this._rtc_peer.setLocalDescription(answer);

        const response = await fetch(CENTRAL_SERVER_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                code: 'answer',
                user_id: this._user_id,
                answer: answer
            })
        });

        if (response.status === 200) {
            console.log('Sent Answer:\n', answer);
        } else {
            console.error('Sent Answer: error');
        }

        this._cur_status = CallLine.Status.Connecting;
        this._on_status_changed.forEach(callback => callback());
    }

    async _processAnswer(json_answer) {
        console.log('Got Answer:\n', json_answer);

        console.assert(this._rtc_peer != null);

        await this._rtc_peer.setRemoteDescription(json_answer);
    }

    _processIce(json_ice_routes) {
        console.log('Got New Ice Routes:\n', json_ice_routes);

        console.assert(this._rtc_peer != null);

        json_ice_routes.forEach(route => this._rtc_peer.addIceCandidate(route));
    }

    _onSuccessfulConnection() {
        clearInterval(this._get_status_timer_id);
        this._get_status_timer_id = -1;

        this._cur_status = CallLine.Status.Call;
        this._on_status_changed.forEach(callback => callback());
        this._on_connected.forEach(callback => callback());
    }

    _processSystemDataChannel(json_data) {
        console.log('system_msg:\n', json_data);

        if (json_data.code === 'reject') {
            this._resetCallLine();
        }
        else if (json_data.code === 'mute_video') {
            this._processSubscriberMute('video', json_data.value);
        }
        else if (json_data.code === 'mute_audio') {
            this._processSubscriberMute('audio', json_data.value);
        }
    }

    _processSubscriberMute(kind, muted) {
        this._video_object.srcObject.getTracks().forEach(track => {
            if (track.kind === kind) {
                track.enabled = !muted;
            }
        });

        this._on_mute_updated.forEach(callback => callback());
    }
}

Object.defineProperty(CallLine.Status, 'Idle', { value: 0, enumerable: true, configurable: false, writable: false })
Object.defineProperty(CallLine.Status, 'WaitForResponse', { value: 1, enumerable: true, configurable: false, writable: false })
Object.defineProperty(CallLine.Status, 'Connecting', { value: 2, enumerable: true, configurable: false, writable: false })
Object.defineProperty(CallLine.Status, 'Call', { value: 3, enumerable: true, configurable: false, writable: false })
