package dev.privateflow.fixtures;

import android.app.Activity;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import android.content.Context;
import android.graphics.Color;
import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.inputmethod.InputMethodManager;
import android.view.inputmethod.InputConnection;
import android.view.inputmethod.InputConnectionWrapper;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.SurroundingText;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Separate, standalone fixture APK; never part of the delivered application. */
public class PlaceholderEditorActivity extends Activity {
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        final String mode=getIntent().getStringExtra("mode")==null ? "normal" : getIntent().getStringExtra("mode");
        final String encoded=getIntent().getStringExtra("initialBase64");
        final String initial=encoded!=null ? new String(Base64.decode(encoded,Base64.DEFAULT),StandardCharsets.UTF_8) :
            (getIntent().getStringExtra("initial")==null ? "" : getIntent().getStringExtra("initial"));
        LinearLayout layout=new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);layout.setPadding(30,190,30,40);layout.setBackgroundColor(Color.rgb(250,249,239));
        TextView title=new TextView(this);title.setText("Insertion fixture: "+mode);title.setTextSize(24);layout.addView(title);
        final TextView observation=new TextView(this);
        observation.setContentDescription("Editor observation");
        observation.setSingleLine(true);observation.setTextSize(10);
        final EditText editor=new EditText(this) {
            private void observe() {
                // Test-only observation of the real Editable, including whitespace
                // and exact cursor indices (accessibility XML normalizes text).
                if(getText()==null)return; // TextView construction may dispatch callbacks.
                String encoded=Base64.encodeToString(getText().toString().getBytes(StandardCharsets.UTF_8),Base64.NO_WRAP);
                observation.setText("editor:"+encoded+":"+getSelectionStart()+":"+getSelectionEnd());
            }
            @Override protected void onSelectionChanged(int start,int end) {
                super.onSelectionChanged(start,end);observe();
            }
            @Override protected void onTextChanged(CharSequence text,int start,int before,int count) {
                super.onTextChanged(text,start,before,count);observe();
            }
            @Override public InputConnection onCreateInputConnection(EditorInfo info) {
                InputConnection connection=super.onCreateInputConnection(info);
                if(connection==null || !mode.equals("no-context"))return connection;
                return new InputConnectionWrapper(connection,false) {
                    @Override public SurroundingText getSurroundingText(int before,int after,int flags) { return null; }
                };
            }
            @Override public void onInitializeAccessibilityNodeInfo(AccessibilityNodeInfo info) {
                super.onInitializeAccessibilityNodeInfo(info);
                if(getText().length()==0 && mode.startsWith("unmarked")) {
                    info.setText("Message");info.setShowingHintText(false);
                    info.setHintText(mode.equals("unmarked-no-hint") ? null : "Message");
                }
            }
        };
        editor.setId(View.generateViewId());editor.setHint("Message");editor.setMinLines(5);editor.setGravity(48);editor.setTextSize(20);
        editor.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);editor.setText(initial);
        layout.addView(editor,new LinearLayout.LayoutParams(-1,-2));layout.addView(observation);
        setContentView(layout);editor.requestFocus();
        editor.postDelayed(new Runnable() { @Override public void run() {
            int start=Math.max(0,Math.min(initial.length(),getIntent().getIntExtra("start",initial.length())));
            int end=Math.max(start,Math.min(initial.length(),getIntent().getIntExtra("end",start)));
            editor.setSelection(start,end);
            ((InputMethodManager)getSystemService(Context.INPUT_METHOD_SERVICE)).showSoftInput(editor,InputMethodManager.SHOW_IMPLICIT);
        }},300);
    }
}
