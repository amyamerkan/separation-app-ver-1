package com.example.demucslite.ui;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.util.AttributeSet;
import android.view.View;

/** Amplitude overview read from each output WAV, with the current playback position. */
public class WaveformView extends View {
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private float[] samples=new float[0];
    private int color=0xFFB5A0FF;
    private float position;
    public WaveformView(Context c, AttributeSet a) { super(c,a); }
    public void setWaveform(float[] value,int tint) { samples=value; color=tint; invalidate(); }
    public void setPosition(float value) { position=value; invalidate(); }
    @Override protected void onDraw(Canvas c) {
        super.onDraw(c);
        if(samples.length==0) return;
        float d=getResources().getDisplayMetrics().density;
        int count=Math.max(1,(int)(getWidth()/(5*d)));
        float spacing=getWidth()/(float)count;
        paint.setStrokeWidth(2*d);paint.setStrokeCap(Paint.Cap.ROUND);
        for(int i=0;i<count;i++) {
            float x=(i+.5f)*spacing;
            float amplitude=Math.max(2*d,samples[Math.min(samples.length-1,i*samples.length/count)]*getHeight()*.45f);
            paint.setColor(color); paint.setAlpha(i/(float)count<=position?255:100);
            c.drawLine(x,getHeight()/2f-amplitude,x,getHeight()/2f+amplitude,paint);
        }
    }
}
