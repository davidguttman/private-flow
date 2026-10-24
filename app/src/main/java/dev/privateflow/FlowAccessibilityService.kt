package dev.privateflow

import android.Manifest
import android.animation.ValueAnimator
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
    private val appearance by lazy { getSharedPreferences("appearance",0) }
    private var idleProgress=0f
    private var idleAnimation:ValueAnimator?=null
    private var touching=false
    private val shrinkAfterIdle=Runnable {
        if(state=="idle" && !touching && bubble!=null && appearance.getBoolean("shrink",true)) {
            idleAnimation?.cancel()
            idleAnimation=ValueAnimator.ofFloat(idleProgress,1f).apply {
                duration=180
                addUpdateListener { idleProgress=it.animatedValue as Float;updateLayout() }
                start()
            }
        }
    }
    private fun sizeScale()=floatArrayOf(.7f,.85f,1f,1.15f)[appearance.getInt("size",1).coerceIn(0,3)]
    private fun scheduleIdleShrink() {
        main.removeCallbacks(shrinkAfterIdle)
        if(state=="idle" && !touching && bubble!=null && appearance.getBoolean("shrink",true))main.postDelayed(shrinkAfterIdle,5000)
    }
    private fun expandBubble() {
        main.removeCallbacks(shrinkAfterIdle);idleAnimation?.cancel();idleAnimation=null;idleProgress=0f
        if(bubble!=null)updateLayout()
    }
    private fun resetIdle() { state="idle";expandBubble();scheduleIdleShrink() }
    fun refreshAppearance() { main.post { expandBubble();scheduleIdleShrink() } }
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
        idleProgress=0f
        val v=BubbleView(this); bubble=v
        val p=WindowManager.LayoutParams(dp(52f),dp(52f),WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,PixelFormat.TRANSLUCENT)
        p.title="Private Flow Bubble"
        p.gravity=Gravity.TOP or Gravity.LEFT;p.x=if(bubbleRight)resources.displayMetrics.widthPixels-dp(60f) else dp(8f);p.y=bubbleY
        try { wm.addView(v,p);updateLayout();scheduleIdleShrink() } catch(e:Exception) { bubble=null }
    }
    private fun hide() { main.removeCallbacks(shrinkAfterIdle);idleAnimation?.cancel();idleAnimation=null;idleProgress=0f;touching=false;bubble?.let { runCatching { wm.removeView(it) } };bubble=null }
    private fun updateLayout() {
        val v=bubble?:return
        val p=v.layoutParams as WindowManager.LayoutParams
        val expanded=state!="idle"
        val scale=sizeScale()
        // Fade the artwork, not the input window. Keep an accessible, stable
        // hit target even when the artwork is a tiny low-opacity dot.
        val touchSide=max(48f,52f*scale)
        p.width=dp(if(expanded)180f*scale else touchSide);p.height=dp(touchSide)
        p.alpha=1f
        v.alpha=appearance.getInt("opacity",100).coerceIn(20,100)/100f
        p.x=if(bubbleRight)resources.displayMetrics.widthPixels-p.width-dp(8f) else dp(8f)
        p.y=bubbleY.coerceIn(dp(35f),resources.displayMetrics.heightPixels-dp(110f))
        wm.updateViewLayout(v,p); v.invalidate()
    }
    private fun fieldText(n:AccessibilityNodeInfo)=if(n.isShowingHintText) "" else n.text?.toString()?:""
    fun startCapture(hold:Boolean) {
        if(state!="idle")return
        expandBubble()
        if(checkSelfPermission(Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED || !getSharedPreferences("connection",0).contains("token")) {
            startActivity(Intent(this,MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));scheduleIdleShrink();return
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
    fun cancel() { generation++;captureActive=false;CaptureService.instance?.finish(true);resetIdle();amplitude=0f;target=null;updateLayout();syncFocus() }
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
        resetIdle();target=null;amplitude=0f;updateLayout();syncFocus()
    } }
    fun failed(message:String,gen:Int) { main.post { if(gen!=generation)return@post;Toast.makeText(this,message,Toast.LENGTH_LONG).show();resetIdle();target=null;captureActive=false;updateLayout();syncFocus() } }
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
                MotionEvent.ACTION_DOWN -> { touching=true;expandBubble();downX=e.rawX;downY=e.rawY;originY=bubbleY;downAt=SystemClock.uptimeMillis();moved=false;holding=false;if(state=="idle")main.postDelayed(longPress,350);return true }
                MotionEvent.ACTION_MOVE -> {
                    if(!holding && state=="idle" && hypot((e.rawX-downX).toDouble(),(e.rawY-downY).toDouble())>dp(10f))moved=true
                    if(moved) { main.removeCallbacks(longPress);bubbleY=originY+(e.rawY-downY).roundToInt();bubbleRight=e.rawX>resources.displayMetrics.widthPixels/2;updateLayout() };return true
                }
                MotionEvent.ACTION_UP -> {
                    main.removeCallbacks(longPress)
                    if(holding)finish()
                    else if(!moved)when(state) { "idle" -> performClick();"recording" -> if(e.x<dp(52f*sizeScale()))cancel() else if(e.x>width-dp(52f*sizeScale()))finish();"transcribing" -> if(e.x<dp(52f*sizeScale()))cancel() }
                    holding=false;touching=false;scheduleIdleShrink();return true
                }
                MotionEvent.ACTION_CANCEL -> { main.removeCallbacks(longPress);if(holding)cancel();holding=false;touching=false;scheduleIdleShrink();return true }
            }
            return true
        }
        override fun onDraw(canvas:Canvas) {
            super.onDraw(canvas)
            val d=resources.displayMetrics.density*sizeScale()
            val w=if(state=="idle")52f else 180f
            canvas.save()
            canvas.translate((width-w*d)/2,(height-52f*d)/2)
            canvas.scale(d,d)
            fun round(l:Float,t:Float,r:Float,b:Float,radius:Float,color:Int) { paint.color=color;paint.style=Paint.Style.FILL;canvas.drawRoundRect(l,t,r,b,radius,radius,paint) }
            paint.strokeWidth=2f;paint.strokeCap=Paint.Cap.ROUND
            if(state=="idle") {
                contentDescription=if(idleProgress>.95f)"Private dictation dot. Tap or hold to record" else "Start private dictation"
                val side=52f-28f*idleProgress
                // Center the shrinking artwork inside the unchanged touch box.
                canvas.translate((52f-side)/2,(52f-side)/2)
                val visual=48f-36f*idleProgress
                val inset=(side-visual)/2
                round(inset,inset,side-inset,side-inset,17f-11f*idleProgress,lavender)
                if(idleProgress<1f) {
                    val bars=floatArrayOf(9f,17f,12f,7f,20f)
                    paint.color=ink;paint.alpha=((1f-idleProgress)*255).roundToInt()
                    val center=side/2
                    bars.forEachIndexed { i,h -> canvas.drawLine(center-8f+i*4,center-h/2,center-8f+i*4,center+h/2,paint) }
                    paint.alpha=255
                }
            } else {
                if(state=="transcribing") {
                    contentDescription="Transcribing audio. Left: cancel"
                    round(2f,2f,50f,50f,24f,lavender)
                    round(55f,2f,w-2f,50f,24f,lavender)
                    paint.color=ink
                    canvas.drawLine(21f,21f,31f,31f,paint);canvas.drawLine(31f,21f,21f,31f,paint)
                    paint.style=Paint.Style.STROKE
                    canvas.drawArc(RectF(65f,19f,79f,33f),(SystemClock.uptimeMillis()%1000)*.36f,270f,false,paint)
                    paint.style=Paint.Style.FILL;paint.textSize=12f
                    canvas.drawText("Transcribing",86f,30f,paint)
                    postInvalidateDelayed(45)
                    canvas.restore()
                    return
                }
                contentDescription="Recording. Left: cancel. Right: done"
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
