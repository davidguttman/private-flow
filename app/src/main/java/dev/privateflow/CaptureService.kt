package dev.privateflow

import android.app.*
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.*
import android.os.*
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.*

class CaptureService:Service() {
    companion object { var instance:CaptureService?=null }
    @Volatile private var active=false
    @Volatile private var recording=false
    @Volatile private var cancelled=false
    private var recorder:AudioRecord?=null
    private var generation=0
    override fun onBind(intent:Intent?)=null
    override fun onStartCommand(intent:Intent?, flags:Int, startId:Int):Int {
        if(active) { FlowAccessibilityService.instance?.let { it.failed("Previous recording is still finishing. Try again shortly.",it.currentGeneration()) };return START_NOT_STICKY };active=true
        instance=this;generation=FlowAccessibilityService.instance?.currentGeneration()?:0
        val manager=getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(NotificationChannel("dictation","Private dictation",NotificationManager.IMPORTANCE_LOW))
        val notification=Notification.Builder(this,"dictation").setContentTitle("Private Flow is listening").setContentText("Tap the bubble's checkmark to finish or X to cancel.").setSmallIcon(android.R.drawable.ic_btn_speak_now).build()
        startForeground(1,notification,ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        recording=true;cancelled=false
        Thread { capture() }.start()
        return START_NOT_STICKY
    }
    fun finish(cancel:Boolean) { if(cancel)cancelled=true;recording=false }
    private fun capture() {
        try {
            if(checkSelfPermission(android.Manifest.permission.RECORD_AUDIO)!=android.content.pm.PackageManager.PERMISSION_GRANTED)error("Microphone permission is required")
            val size=max(4096,AudioRecord.getMinBufferSize(16000,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT))
            val mic=AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION,16000,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT,size)
            recorder=mic
            require(mic.state==AudioRecord.STATE_INITIALIZED) { "Microphone unavailable" }
            val pcm=ByteArrayOutputStream();val buffer=ByteArray(size)
            mic.startRecording()
            val limit=16000*2*300
            while(recording && pcm.size()<limit) {
                val n=mic.read(buffer,0,buffer.size)
                if(n<0)error("Microphone read failed ($n)")
                if(n>0) {
                    pcm.write(buffer,0,n)
                    var energy=0.0
                    for(i in 0 until n-1 step 2) { val s=((buffer[i].toInt() and 255) or (buffer[i+1].toInt() shl 8)).toShort().toDouble();energy+=s*s }
                    FlowAccessibilityService.instance?.amplitude=(sqrt(energy/(n/2))/5000).toFloat()
                }
            }
            mic.stop();mic.release();recorder=null
            if(!cancelled) {
                Handler(Looper.getMainLooper()).post { FlowAccessibilityService.instance?.finish() }
                val data=pcm.toByteArray()
                require(data.size>=3200) { "Recording too short — try again" }
                val header=ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
                header.put("RIFF".toByteArray()).putInt(36+data.size).put("WAVEfmt ".toByteArray()).putInt(16).putShort(1).putShort(1).putInt(16000).putInt(32000).putShort(2).putShort(16).put("data".toByteArray()).putInt(data.size)
                val text=Bridge.transcribe(this,header.array()+data)
                if(!cancelled)FlowAccessibilityService.instance?.captured(text,generation)
            }
        } catch(e:Exception) {
            if(!cancelled)FlowAccessibilityService.instance?.failed(e.message?:"Dictation failed",generation)
        } finally {
            runCatching { recorder?.stop() };recorder?.release();recorder=null;recording=false
            Handler(Looper.getMainLooper()).post { stopForeground(STOP_FOREGROUND_REMOVE);stopSelf() }
        }
    }
    override fun onDestroy() { cancelled=true;recording=false;active=false;instance=null;super.onDestroy() }
}
