package dev.privateflow.fixtures;

import android.app.Activity;
import android.content.Context;
import android.graphics.Color;
import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.inputmethod.InputMethodManager;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Separate, standalone fixture APK; never part of the delivered application. */
public class PlaceholderEditorActivity extends Activity {
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        final String mode=getIntent().getStringExtra("mode")==null ? "normal" : getIntent().getStringExtra("mode");
        final String initial=getIntent().getStringExtra("initial")==null ? "" : getIntent().getStringExtra("initial");
        LinearLayout layout=new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);layout.setPadding(30,190,30,40);layout.setBackgroundColor(Color.rgb(250,249,239));
        TextView title=new TextView(this);title.setText("Insertion fixture: "+mode);title.setTextSize(24);layout.addView(title);
        final EditText editor=new EditText(this) {
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
        layout.addView(editor,new LinearLayout.LayoutParams(-1,-2));setContentView(layout);editor.requestFocus();
        editor.postDelayed(new Runnable() { @Override public void run() {
            int start=Math.max(0,Math.min(initial.length(),getIntent().getIntExtra("start",initial.length())));
            int end=Math.max(start,Math.min(initial.length(),getIntent().getIntExtra("end",start)));
            editor.setSelection(start,end);
            ((InputMethodManager)getSystemService(Context.INPUT_METHOD_SERVICE)).showSoftInput(editor,InputMethodManager.SHOW_IMPLICIT);
        }},300);
    }
}
