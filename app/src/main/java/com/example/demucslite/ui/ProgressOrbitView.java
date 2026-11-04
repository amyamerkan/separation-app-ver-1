package com.example.demucslite.ui;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.os.SystemClock;
import android.util.AttributeSet;
import android.view.View;

public class ProgressOrbitView extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private float progress = -1;
    private final RectF arc = new RectF();
    public ProgressOrbitView(Context context, AttributeSet attrs) { super(context,attrs); }
    public void setProgress(float value) { progress=value; invalidate(); }
    @Override protected void onDraw(Canvas c) {
        super.onDraw(c);
        float d=getResources().getDisplayMetrics().density;
        float cx=getWidth()/2f,cy=getHeight()/2f,r=Math.min(getWidth()/2f-16*d,87*d);
        paint.setStyle(Paint.Style.STROKE); paint.setStrokeWidth(d);
        paint.setColor(0xFF2A2838); c.drawCircle(cx,cy,r+16*d,paint);
        paint.setStrokeWidth(7*d); paint.setColor(0xFF302B40); c.drawCircle(cx,cy,r,paint);
        paint.setStrokeCap(Paint.Cap.ROUND); paint.setColor(0xFFB5A0FF);
        float start=progress<0 ? (SystemClock.uptimeMillis()%2400)/2400f*360f-90 : -90;
        float sweep=progress<0 ? 94 : Math.max(3,progress*3.6f);
        arc.set(cx-r,cy-r,cx+r,cy+r);
        c.drawArc(arc,start,sweep,false,paint);
        double angle=Math.toRadians(start+sweep);
        paint.setStyle(Paint.Style.FILL); paint.setColor(0xFFCDF5A2);
        c.drawCircle(cx+(float)Math.cos(angle)*r,cy+(float)Math.sin(angle)*r,5*d,paint);
        if(progress<0 && isShown()) postInvalidateOnAnimation();
    }
}
