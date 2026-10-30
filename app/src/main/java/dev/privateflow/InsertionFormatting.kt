package dev.privateflow

/** Pure, phone-local insertion policy. Null context means preserve original case. */
internal object InsertionFormatting {
    fun beforeSelection(text:String, selectionStart:Int, selectionEnd:Int, offset:Int):String? {
        if(selectionStart !in 0..text.length || selectionEnd !in 0..text.length)return null
        val before=text.substring(0,minOf(selectionStart,selectionEnd))
        // An empty/whitespace-only truncated window cannot establish field start.
        if(offset!=0 && before.all { it.isWhitespace() } && before.none(::paragraphBreak))return null
        return before
    }

    fun format(transcript:String, before:String?):String {
        if(transcript.isBlank())return ""
        // Normalize only literal trailing spaces, retaining punctuation/newlines.
        var result=transcript.trimEnd(' ')
        if(before!=null && midSentence(before)) {
            var index=0
            while(index<result.length) {
                val codePoint=result.codePointAt(index)
                val count=Character.charCount(codePoint)
                if(Character.isLetter(codePoint)) {
                    result=result.substring(0,index)+result.substring(index,index+count).lowercase()+result.substring(index+count)
                    break
                }
                index+=count
            }
        }
        return result+" "
    }

    private fun midSentence(before:String):Boolean {
        for(c in before.reversed()) {
            if(paragraphBreak(c))return false
            // Quotes/brackets do not hide sentence punctuation or paragraph/field start.
            if(c.isWhitespace() || c in "\"'“”‘’«»‹›()[]{}")continue
            return c!='.' && c!='!' && c!='?'
        }
        return false
    }

    private fun paragraphBreak(c:Char)=c=='\n' || c=='\r' || c=='\u2028' || c=='\u2029'
}
