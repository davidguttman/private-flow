package dev.privateflow

import android.content.SharedPreferences
import kotlin.math.roundToInt

internal class BubblePosition(private val preferences:SharedPreferences) {
    data class Position(val right:Boolean,val y:Int)

    fun restore(displayHeight:Int,minY:Int,maxY:Int):Position {
        val fraction=preferences.getFloat("bubble_y_fraction",.5f).let { if(it.isFinite())it.coerceIn(0f,1f) else .5f }
        return Position(preferences.getBoolean("bubble_right",true),(fraction*displayHeight).roundToInt().coerceIn(minY,maxY))
    }

    fun save(right:Boolean,y:Int,displayHeight:Int,minY:Int,maxY:Int) {
        // Save the visible resting position, not an out-of-bounds finger location.
        // Relative height also keeps a saved position useful after display changes.
        val fraction=if(displayHeight>0)y.coerceIn(minY,maxY).toFloat()/displayHeight else .5f
        preferences.edit().putBoolean("bubble_right",right).putFloat("bubble_y_fraction",fraction).apply()
    }
}
