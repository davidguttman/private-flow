package dev.privateflow

import android.Manifest
import android.accessibilityservice.AccessibilityService
import android.content.*
import android.content.pm.PackageManager
import android.graphics.*
import android.os.*
import android.provider.Settings
import android.view.*
import android.view.accessibility.*
import android.widget.Toast
import kotlin.math.*

class FlowAccessibilityService : AccessibilityService() {
    companion object { var instance:FlowAccessibilityService?=null }
    private val main=Handler(Looper.getMainLooper())
    private lateinit var wm:WindowManager
    private var bubble:BubbleView?=null
    private var target:AccessibilityNodeInfo?=null
    private var targetText=""
    private var targetSelection=0 to 0
    private var targetWindow=-1
    private var targetId:String?=null
    private var state="idle"
    private var generation=0
    private var sessionGeneration=0
    private var bubbleY=0
    private var bubbleRight=true
    private var captureActive=false
    var amplitude=0f
    override fun onServiceConnected() { instance=this; wm=getSystemService(WINDOW_SERVICE) as WindowManager; bubbleY=resources.displayMetrics.heightPixels/2; syncFocus() }
    override fun onAccessibilityEvent(event:AccessibilityEvent?) { if(state=="idle")syncFocus() }
    private fun focused():AccessibilityNodeInfo? {
        for(w in windows) { if(w.type==AccessibilityWindowInfo.TYPE_INPUT_METHOD || w.type==AccessibilityWindowInfo.TYPE_ACCESSIBILITY_OVERLAY)continue
            if(!w.isFocused && !w.isActive)continue
            val n=w.root?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
            if(n!=null && n.isFocused)return n
        }
        return rootInActiveWindow?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
    }
    private fun eligible(n:AccessibilityNodeInfo?):Boolean {
        if(n==null || !n.isEditable || !n.isVisibleToUser || n.isPassword)return false
        val type=n.inputType
        if(type and 15 in listOf(2,3,4))return false
        val variation=type and 0xff0
        return variation !in listOf(0x80,0x90,0xe0)
    }
    private fun syncFocus() {
        if(!Settings.canDrawOverlays(this)) { hide(); return }
        val n=focused()
        if(eligible(n) && windows.any { it.type==AccessibilityWindowInfo.TYPE_INPUT_METHOD })show() else hide()
    }
    private fun dp(v:Float)=(v*resources.displayMetrics.density).roundToInt()
    private fun show() {
        if(bubble!=null)return
        val v=BubbleView(this); bubble=v
        val p=WindowManager.LayoutParams(dp(52f),dp(52f),WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,PixelFormat.TRANSLUCENT)
        p.title="Private Flow Bubble"
        p.gravity=Gravity.TOP or Gravity.LEFT;p.x=if(bubbleRight)resources.displayMetrics.widthPixels-dp(60f) else dp(8f);p.y=bubbleY
        try { wm.addView(v,p) } catch(e:Exception) { bubble=null }
    }
    private fun hide() { bubble?.let { runCatching { wm.removeView(it) } };bubble=null }
    private fun updateLayout() {
        val v=bubble?:return
        val p=v.layoutParams as WindowManager.LayoutParams
        val expanded=state!="idle"
        p.width=dp(if(expanded)180f else 52f);p.height=dp(52f)
        p.x=if(bubbleRight)resources.displayMetrics.widthPixels-p.width-dp(8f) else dp(8f)
        p.y=bubbleY.coerceIn(dp(35f),resources.displayMetrics.heightPixels-dp(110f))
        wm.updateViewLayout(v,p); v.invalidate()
    }
    private fun fieldText(n:AccessibilityNodeInfo)=if(n.isShowingHintText) "" else n.text?.toString()?:""
    fun startCapture(hold:Boolean) {
        if(state!="idle")return
        if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED || !getSharedPreferences("connection",0).contains("token")) {
            startActivity(Intent(this,MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));return
        }
        val n=focused()
        if(!eligible(n))return
        target=n;targetText=fieldText(n!!);targetSelection=n.textSelectionStart to n.textSelectionEnd;targetWindow=n.windowId;targetId=n.viewIdResourceName
        state=if(hold)"holding" else "recording"; generation++;sessionGeneration=generation;captureActive=true; updateLayout()
        try { startForegroundService(Intent(this,CaptureService::class.java)) }
        catch(e:Exception) { failed("Can't start microphone: ${e.message}",sessionGeneration) }
    }
    fun finish() {
        if(state!="recording" && state!="holding")return
        state="transcribing";captureActive=false;updateLayout();CaptureService.instance?.finish(false)
    }
    fun cancel() { generation++;captureActive=false;CaptureService.instance?.finish(true);state="idle";amplitude=0f;target=null;updateLayout();syncFocus() }
    fun currentGeneration()=sessionGeneration
    fun captured(text:String, gen:Int) { main.post {
        if(gen!=generation)return@post
        val n=target
        val current=focused()
        val stable=n!=null && n.refresh() && n.isFocused && current?.windowId==targetWindow &&
            (targetId==null || current.viewIdResourceName==targetId) && eligible(n) &&
            fieldText(n)==targetText && n.textSelectionStart==targetSelection.first && n.textSelectionEnd==targetSelection.second
        var inserted=false
        if(stable) {
            val start=targetSelection.first.coerceIn(0,targetText.length)
            val end=targetSelection.second.coerceIn(start,targetText.length)
            val result=targetText.substring(0,start)+text+targetText.substring(end)
            inserted=n!!.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,Bundle().apply { putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,result) })
            if(inserted)n.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION,Bundle().apply { putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT,start+text.length);putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT,start+text.length) })
        }
        if(!inserted && text.isNotBlank()) {
            (getSystemService(CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("Private dictation",text))
            Toast.makeText(this,"Text field changed. Transcript copied — paste where you want it.",Toast.LENGTH_LONG).show()
        }
        state="idle";target=null;amplitude=0f;updateLayout();syncFocus()
    } }
    fun failed(message:String,gen:Int) { main.post { if(gen!=generation)return@post;Toast.makeText(this,message,Toast.LENGTH_LONG).show();state="idle";target=null;captureActive=false;updateLayout();syncFocus() } }
    override fun onInterrupt() { cancel() }
    override fun onDestroy() { cancel();hide();instance=null;super.onDestroy() }

    inner class BubbleView(context:Context):View(context) {
        private val paint=Paint(Paint.ANTI_ALIAS_FLAG)
        private val lavender=Color.rgb(234,205,246)
        private val cream=Color.rgb(252,253,226)
        private val ink=Color.rgb(28,22,31)
        private var downX=0f;private var downY=0f;private var originY=0;private var moved=false;private var holding=false
        private var downAt=0L
        private val longPress=Runnable { if(!moved && state=="idle") { holding=true;performHapticFeedback(HapticFeedbackConstants.LONG_PRESS);startCapture(true) } }
        init { contentDescription="Start private dictation";isClickable=true;importantForAccessibility=IMPORTANT_FOR_ACCESSIBILITY_YES }
        override fun performClick():Boolean { super.performClick();if(state=="idle")startCapture(false);return true }
        override fun onTouchEvent(e:MotionEvent):Boolean {
            when(e.actionMasked) {
                MotionEvent.ACTION_DOWN -> { downX=e.rawX;downY=e.rawY;originY=bubbleY;downAt=SystemClock.uptimeMillis();moved=false;holding=false;if(state=="idle")main.postDelayed(longPress,350);return true }
                MotionEvent.ACTION_MOVE -> {
                    if(!holding && state=="idle" && hypot((e.rawX-downX).toDouble(),(e.rawY-downY).toDouble())>dp(10f))moved=true
                    if(moved) { main.removeCallbacks(longPress);bubbleY=originY+(e.rawY-downY).roundToInt();bubbleRight=e.rawX>resources.displayMetrics.widthPixels/2;updateLayout() };return true
                }
                MotionEvent.ACTION_UP -> {
                    main.removeCallbacks(longPress)
                    if(holding)finish()
                    else if(!moved)when(state) { "idle" -> performClick();"recording" -> if(e.x<dp(52f))cancel() else if(e.x>width-dp(52f))finish();"transcribing" -> if(e.x<dp(52f))cancel() }
                    holding=false;return true
                }
                MotionEvent.ACTION_CANCEL -> { main.removeCallbacks(longPress);if(holding)cancel();holding=false;return true }
            }
            return true
        }
        override fun onDraw(canvas:Canvas) {
            super.onDraw(canvas)
            val d=resources.displayMetrics.density
            canvas.save();canvas.scale(d,d)
            val w=width/d
            fun round(l:Float,t:Float,r:Float,b:Float,radius:Float,color:Int) { paint.color=color;paint.style=Paint.Style.FILL;canvas.drawRoundRect(l,t,r,b,radius,radius,paint) }
            paint.strokeWidth=2f;paint.strokeCap=Paint.Cap.ROUND
            if(state=="idle") {
                contentDescription="Start private dictation"
                round(2f,2f,50f,50f,17f,lavender)
                val bars=floatArrayOf(9f,17f,12f,7f,20f)
                paint.color=ink
                bars.forEachIndexed { i,h -> canvas.drawLine(18f+i*4,26f-h/2,18f+i*4,26f+h/2,paint) }
            } else {
                contentDescription=if(state=="transcribing")"Transcribing. Left: cancel" else "Recording. Left: cancel. Right: done"
                round(2f,2f,50f,50f,24f,lavender)
                round(55f,2f,w-55f,50f,24f,lavender)
                if(state!="holding")round(w-50f,2f,w-2f,50f,24f,cream)
                paint.color=ink;canvas.drawLine(21f,21f,31f,31f,paint);canvas.drawLine(31f,21f,21f,31f,paint)
                if(state!="holding") { canvas.drawLine(w-32f,26f,w-27f,31f,paint);canvas.drawLine(w-27f,31f,w-19f,22f,paint) }
                val now=SystemClock.uptimeMillis()/110.0
                val center=w/2
                for(i in -6..6) {
                    val height=if(state=="transcribing")2f+(sin(now+i*.6)*2).toFloat().coerceAtLeast(0f) else 3f+(amplitude.coerceIn(0f,1f)*22f*(.4f+.6f*abs(sin(now+i*.9)).toFloat()))
                    canvas.drawLine(center+i*3.8f,26f-height/2,center+i*3.8f,26f+height/2,paint)
                }
                postInvalidateDelayed(45)
            }
            canvas.restore()
        }
    }
}
