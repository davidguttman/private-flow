package dev.privateflow

import org.junit.Assert.assertEquals
import org.junit.Test

class InsertionFormattingTest {
    private fun format(text:String, before:String?=null)=InsertionFormatting.format(text,before)

    @Test fun alwaysAppendsLiteralSpaceAndBlankIsNoOp() {
        assertEquals("Hello. ",format("Hello."))
        assertEquals("Hello ",format("Hello   "))
        assertEquals("Hello\n ",format("Hello\n")) // preserve paragraph breaks
        listOf("", " ", "\t\n").forEach { assertEquals("",format(it,"before ")) }
    }

    @Test fun lowercasesFirstLetterOnlyWithoutWordExceptions() {
        mapOf("Alice Smith" to "alice Smith ", "NASA" to "nASA ", "I agree" to "i agree ",
            "I'm Ready." to "i'm Ready. ", "“Hello WORLD!”" to "“hello WORLD!” ",
            "123 ABC" to "123 aBC ", "Éclair" to "éclair ", "123!" to "123! ")
            .forEach { (text,expected) -> assertEquals(expected,format(text,"We met ")) }
        assertEquals("hello ",format("Hello","word")) // no leading boundary spacing
        assertEquals("hello ",format("Hello","word,  "))
    }

    @Test fun preservesCaseAtFieldParagraphAndSentenceStarts() {
        listOf("", " \t", "Done. ", "Done!\t", "Done?", "old\n", "old\n  ", "old\r\n\t", "old\u2029 ")
            .forEach { before -> assertEquals(before,"Alice NASA. ",format("Alice NASA.",before)) }
        assertEquals("Alice ",format("Alice",null))
    }

    @Test fun ignoresQuotesAndBracketsAroundSentenceBoundaries() {
        listOf("He said “Done!” ", "He said \"Done?\" ", "He said ‘Done.’ ",
            "(Done.) ", "[Done!] ", "{Done?} ", "He said («Done!») ")
            .forEach { before -> assertEquals(before,"Alice NASA. ",format("Alice NASA.",before)) }
    }

    @Test fun ignoresOpeningQuotesAndBracketsAtFieldOrParagraphStartOnly() {
        listOf("“", "\"", "‘", "'", "(", "[", "{", "«", "‹", "(“ ", "old\n  (“", "old\u2029 [\"")
            .forEach { before -> assertEquals(before,"Alice NASA. ",format("Alice NASA.",before)) }
        listOf("He said “Hello ", "He said \"Hello ", "He said (“", "He said (Hello) ")
            .forEach { before -> assertEquals(before,"alice NASA. ",format("Alice NASA.",before)) }
    }

    @Test fun usesSelectionStartNotEndOrSuffixAndHandlesReversedSelection() {
        assertEquals("Before ",InsertionFormatting.beforeSelection("Before old after",7,10,0))
        assertEquals("Before ",InsertionFormatting.beforeSelection("Before old after",10,7,0))
        assertEquals("",InsertionFormatting.beforeSelection("Message",0,0,0))
        assertEquals("word ",InsertionFormatting.beforeSelection("word ,suffix",5,5,100))
        assertEquals("word ",InsertionFormatting.beforeSelection("word  suffix",5,5,100))
    }

    @Test fun invalidOrInsufficientContextIsUnknown() {
        listOf(-1 to 0, 0 to -1, 4 to 4, 0 to 4).forEach { (start,end) ->
            assertEquals(null,InsertionFormatting.beforeSelection("abc",start,end,0))
        }
        assertEquals(null,InsertionFormatting.beforeSelection("   ",3,3,100))
        assertEquals(null,InsertionFormatting.beforeSelection("",0,0,-1))
        assertEquals(null,InsertionFormatting.beforeSelection("after",0,0,50))
        assertEquals("",InsertionFormatting.beforeSelection("",0,0,0))
        assertEquals("abc ",InsertionFormatting.beforeSelection("abc ",4,4,-1))
        assertEquals("\n  ",InsertionFormatting.beforeSelection("\n  ",3,3,100))
    }

    @Test fun preservesSuffixAndReplacementWithCursorImmediatelyAfterNewSpace() {
        listOf("Before after" to (7 to 7), "Before  after" to (7 to 7),
            "Before ,after" to (7 to 7), "Before old after" to (7 to 10),
            "Message" to (0 to 0)).forEach { (editor,selection) ->
            val (start,end)=selection
            val inserted=format("Alice.",InsertionFormatting.beforeSelection(editor,start,end,0))
            val expected=if(start==0) "Alice. " else "alice. "
            assertEquals(expected,inserted)
            val result=editor.take(start)+inserted+editor.substring(end)
            val cursor=start+inserted.length
            assertEquals(' ',result[cursor-1])
            assertEquals(editor.substring(end),result.substring(cursor))
        }
    }
}
