package dev.privateflow

import android.content.Context
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import org.json.JSONObject

object Bridge {
    fun validateEndpoint(url:String) {
        val u=URI(url)
        require(u.rawUserInfo==null && u.rawQuery==null && u.rawFragment==null && (u.path.isNullOrEmpty() || u.path=="/")) { "Use only the computer address and port" }
        val h=u.host ?: error("Enter your computer's Tailscale address")
        val oct=h.split('.').mapNotNull { it.toIntOrNull() }
        val tail=oct.size==4 && oct[0]==100 && oct[1] in 64..127 && oct.all { it in 0..255 }
        val loop=h=="127.0.0.1" || h=="localhost" || h=="10.0.2.2"
        require(u.scheme=="https" || (u.scheme=="http" && (tail || loop))) { "Use HTTPS or your encrypted Tailscale IP" }
    }
    fun request(endpoint:String,path:String,body:ByteArray?,token:String?,contentType:String="audio/wav"):String {
        validateEndpoint(endpoint)
        val c=URL(endpoint+path).openConnection() as HttpURLConnection
        try {
            c.connectTimeout=10000; c.readTimeout=120000; c.instanceFollowRedirects=false
            if(token!=null)c.setRequestProperty("Authorization","Bearer $token")
            if(body!=null) { c.requestMethod="POST"; c.doOutput=true; c.setRequestProperty("Content-Type",contentType); c.setFixedLengthStreamingMode(body.size); c.outputStream.use { it.write(body) } }
            val code=c.responseCode
            if(code !in 200..299) {
                val raw=c.errorStream?.bufferedReader()?.use { it.readText() } ?: "Connection failed ($code)"
                val message=runCatching { JSONObject(raw).getString("error") }.getOrDefault("Connection failed ($code)")
                error(message)
            }
            return c.inputStream.bufferedReader().use { it.readText() }
        } finally { c.disconnect() }
    }
    fun health(context:Context) { val p=context.getSharedPreferences("connection",0); request(p.getString("url","")!!,"/health",null,p.getString("token",null)) }
    fun transcribe(context:Context,wav:ByteArray):String {
        val p=context.getSharedPreferences("connection",0)
        val token=p.getString("token",null) ?: error("Pair your computer in Private Flow first")
        return JSONObject(request(p.getString("url","")!!,"/transcribe",wav,token)).getString("text")
    }
}
