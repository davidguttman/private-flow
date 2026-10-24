package dev.privateflow

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.text.InputType
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.widget.*
import org.json.JSONObject

class MainActivity : Activity() {
    private lateinit var status: TextView
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
        window.statusBarColor = Color.rgb(250,249,239)
        window.navigationBarColor = Color.rgb(250,249,239)
        val prefs = getSharedPreferences("connection", MODE_PRIVATE)
        val body = LinearLayout(this).apply { orientation=LinearLayout.VERTICAL; setPadding(28,64,28,30); setBackgroundColor(Color.rgb(250,249,239)) }
        val scroll=ScrollView(this).apply { addView(body) }; setContentView(scroll)
        body.setOnApplyWindowInsetsListener { v,insets -> val bars=insets.getInsets(WindowInsets.Type.systemBars());v.setPadding(28,bars.top+40,28,bars.bottom+30);insets }
        fun label(text:String, size:Float=16f)=TextView(this).apply { this.text=text; textSize=size; setTextColor(Color.rgb(25,25,25)); setPadding(0,12,0,12); body.addView(this) }
        label("Private Flow",36f).setTypeface(null,Typeface.BOLD)
        label("Your voice. Your machine.",20f)
        label("Keep your keyboard. Tap the floating bubble, speak, then tap ✓ to insert your words.")
        status=label("",14f)
        fun button(text:String, action:()->Unit) { body.addView(Button(this).apply { this.text=text; isAllCaps=false; setOnClickListener { action() } }) }
        button("1 · Allow microphone") { requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO,Manifest.permission.POST_NOTIFICATIONS),1) }
        button("2 · Allow floating bubble") { startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,Uri.parse("package:$packageName"))) }
        button("3 · Enable Private Flow accessibility") { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
        label("Connect your computer",22f)
        val url=EditText(this).apply { hint="http://100.x.x.x:8767"; setSingleLine(); inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI; setText(prefs.getString("url","")); body.addView(this) }
        val token=EditText(this).apply { hint="Pairing code"; setSingleLine(); inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD; body.addView(this) }
        button("Pair with computer") {
            val endpoint=url.text.toString().trim().trimEnd('/')
            try { Bridge.validateEndpoint(endpoint) } catch(e:Exception) { toast(e.message ?: "Invalid address"); return@button }
            val code=token.text.toString().trim()
            if(code.isEmpty()) { toast("Enter the pairing code shown on your computer"); return@button }
            Thread {
                try {
                    val result=Bridge.request(endpoint,"/pair",JSONObject().put("code",code).toString().toByteArray(),null,"application/json")
                    val auth=JSONObject(result).getString("token")
                    prefs.edit().putString("url",endpoint).putString("token",auth).apply()
                    runOnUiThread { token.setText(""); toast("Paired. Speech stays on your computer."); refresh() }
                } catch(e:Exception) { runOnUiThread { toast(e.message ?: "Pairing failed") } }
            }.start()
        }
        button("Check connection") {
            Thread { try { Bridge.health(this); runOnUiThread { toast("Connected to your private Voxtype bridge") } } catch(e:Exception) { runOnUiThread { toast(e.message ?: "Not connected") } } }.start()
        }
        button("Try dictation") { startActivity(Intent(this,TestEditorActivity::class.java)) }
        label("No cloud fallback. No analytics. Recordings are discarded after transcription. Your computer must be awake and reachable through Tailscale.",14f)
    }
    override fun onResume() { super.onResume(); refresh() }
    private fun refresh() { if(!::status.isInitialized)return; status.text="Microphone: ${if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)==PackageManager.PERMISSION_GRANTED) "✓" else "needed"}    Bubble: ${if(Settings.canDrawOverlays(this)) "✓" else "needed"}\nAccessibility: ${if(FlowAccessibilityService.instance!=null) "✓" else "needed"}    Paired: ${if(getSharedPreferences("connection",0).contains("token")) "✓" else "not yet"}" }
    private fun toast(s:String)=Toast.makeText(this,s,Toast.LENGTH_LONG).show()
}

class TestEditorActivity : Activity() {
    override fun onCreate(state:Bundle?) {
        super.onCreate(state)
        val layout=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL; setPadding(28,70,28,28); setBackgroundColor(Color.rgb(250,249,239)) }
        layout.addView(TextView(this).apply { text="Try your private dictation"; textSize=26f; setPadding(0,0,0,24) })
        layout.addView(EditText(this).apply { hint="Tap here, then tap the bubble"; id=View.generateViewId(); minLines=6; gravity=48; inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE; textSize=20f },LinearLayout.LayoutParams(-1,-2))
        setContentView(layout)
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
        layout.setOnApplyWindowInsetsListener { v,insets -> val bars=insets.getInsets(WindowInsets.Type.systemBars());v.setPadding(28,bars.top+40,28,bars.bottom+28);insets }
    }
}
