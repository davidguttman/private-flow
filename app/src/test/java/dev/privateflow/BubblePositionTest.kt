package dev.privateflow

import android.content.SharedPreferences
import org.junit.Assert.*
import org.junit.Test
import java.lang.reflect.Proxy

class BubblePositionTest {
    // Exercise the real SharedPreferences keys/editor without an Android runtime
    // dependency. A fresh store sees only the previous editor's persisted writes.
    private class Preferences {
        val disk=mutableMapOf<String,Any>()
        var writes=0
        fun open():SharedPreferences {
            val pending=mutableMapOf<String,Any>()
            val editor=Proxy.newProxyInstance(SharedPreferences.Editor::class.java.classLoader,
                arrayOf(SharedPreferences.Editor::class.java)) { proxy,method,args ->
                when(method.name) {
                    "putBoolean","putFloat" -> { pending[args!![0] as String]=args[1];proxy }
                    "apply","commit" -> { disk.putAll(pending);pending.clear();writes++;if(method.name=="commit")true else null }
                    else -> error("Unexpected editor call: ${method.name}")
                }
            } as SharedPreferences.Editor
            return Proxy.newProxyInstance(SharedPreferences::class.java.classLoader,
                arrayOf(SharedPreferences::class.java)) { _,method,args ->
                when(method.name) {
                    "getBoolean","getFloat" -> disk[args!![0]] ?: args[1]
                    "contains" -> disk.containsKey(args!![0])
                    "edit" -> editor
                    else -> error("Unexpected preferences call: ${method.name}")
                }
            } as SharedPreferences
        }
    }

    @Test fun firstRunKeepsRightHalfScreenDefaultWithoutWriting() {
        val prefs=Preferences()
        val position=BubblePosition(prefs.open()).restore(2000,70,1780)
        assertTrue(position.right)
        assertEquals(1000,position.y)
        assertEquals(0,prefs.writes)
        assertTrue(prefs.disk.isEmpty())
    }

    @Test fun completedDragRestoresBothSidesThroughFreshPreferences() {
        val prefs=Preferences()
        listOf(false to 340,true to 1570).forEach { (right,y) ->
            BubblePosition(prefs.open()).save(right,y,2000,70,1780)
            val restored=BubblePosition(prefs.open()).restore(2000,70,1780)
            assertEquals(right,restored.right)
            assertEquals(y,restored.y)
        }
        assertEquals(2,prefs.writes)
        assertEquals(setOf("bubble_right","bubble_y_fraction"),prefs.disk.keys)
    }

    @Test fun restoresRelativeVerticalPlacementOnSmallerDisplay() {
        val prefs=Preferences()
        BubblePosition(prefs.open()).save(false,1500,2000,70,1780)
        val restored=BubblePosition(prefs.open()).restore(1000,35,890)
        assertFalse(restored.right)
        assertEquals(750,restored.y)
    }

    @Test fun savesVisibleClampedPositionRatherThanOffscreenDragCoordinates() {
        val prefs=Preferences()
        val store=BubblePosition(prefs.open())
        store.save(false,-500,2000,70,1780)
        assertEquals(70,BubblePosition(prefs.open()).restore(2000,70,1780).y)
        store.save(true,5000,2000,70,1780)
        assertEquals(1780,BubblePosition(prefs.open()).restore(2000,70,1780).y)
        assertEquals(500,BubblePosition(prefs.open()).restore(1000,35,500).y)
    }

    @Test fun tinyDisplayAndInvalidSavedFractionsAreSafe() {
        val prefs=Preferences()
        val store=BubblePosition(prefs.open())
        assertEquals(0,store.restore(0,0,0).y)
        store.save(false,100,0,0,0)
        assertEquals(0,store.restore(0,0,0).y)
        listOf(Float.NaN,Float.POSITIVE_INFINITY,Float.NEGATIVE_INFINITY).forEach {
            prefs.disk["bubble_y_fraction"]=it
            assertEquals(1000,store.restore(2000,70,1780).y)
        }
        prefs.disk["bubble_y_fraction"]=-10f
        assertEquals(70,store.restore(2000,70,1780).y)
        prefs.disk["bubble_y_fraction"]=10f
        assertEquals(1780,store.restore(2000,70,1780).y)
    }
}
