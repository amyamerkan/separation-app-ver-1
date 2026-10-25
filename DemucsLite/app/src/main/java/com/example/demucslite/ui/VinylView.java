package com.example.demucslite.ui;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.util.AttributeSet;
import android.view.View;

/** Original vector artwork, rendered crisply at every display density. */
public class VinylView extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();

    public VinylView(Context context, AttributeSet attrs) { super(context, attrs); }

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        float w = getWidth(), h = getHeight(), u = w / 360f;
        canvas.save();
        path.reset();
        path.addRoundRect(new RectF(0, 0, w, h), 28 * u, 28 * u, Path.Direction.CW);
        canvas.clipPath(path);
        paint.setColor(Color.rgb(181, 160, 255));
        canvas.drawPaint(paint);
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(u);
        paint.setColor(0x557767B0);
        for (int i = 0; i < 5; i++) {
            canvas.drawOval(new RectF(-110*u, h*.18f+i*17*u, w+60*u, h*.92f+i*17*u), paint);
        }
        paint.setStyle(Paint.Style.FILL);
        label(canvas, "SPLIT IT.", 22*u, 32*u, 13*u, 0xFF272033, true);
        label(canvas, "FEEL IT.", 22*u, 48*u, 13*u, 0xFF272033, true);
        float cx = w*.62f, cy = h*.51f, radius = Math.min(w*.34f, h*.48f);
        paint.setColor(0x33251D3C);
        canvas.drawCircle(cx+5*u, cy+9*u, radius, paint);
        paint.setColor(0xFF211D2D);
        canvas.drawCircle(cx, cy, radius, paint);
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(.8f*u);
        for (int i=0; i<15; i++) {
            paint.setColor(i%3==0 ? 0xFF4A405C : 0xFF332C44);
            canvas.drawCircle(cx, cy, radius-8*u-i*4.1f*u, paint);
        }
        paint.setStyle(Paint.Style.FILL);
        paint.setColor(0xFFCDF5A2);
        canvas.drawCircle(cx, cy, radius*.34f, paint);
        paint.setColor(0xFF211D2D);
        paint.setStrokeCap(Paint.Cap.ROUND);
        paint.setStrokeWidth(3*u);
        for(int i=0;i<5;i++) {
            float x=cx+(i-2)*8*u, bar=(i==2?19:i%2==0?7:13)*u;
            canvas.drawLine(x,cy-bar,x,cy+bar,paint);
        }
        canvas.save();
        canvas.rotate(-12, 74*u, h*.66f);
        paint.setColor(0xFFFFBD9A);
        canvas.drawRoundRect(new RectF(16*u,h*.53f,129*u,h*.80f),12*u,12*u,paint);
        label(canvas,"4 STEMS",28*u,h*.53f+23*u,18*u,0xFF25202C,true);
        label(canvas,"1 VIBE ↗",28*u,h*.53f+43*u,15*u,0xFF25202C,true);
        canvas.restore();
        star(canvas, w-29*u, 31*u, 12*u,0xFF272033);
        star(canvas, 144*u, 50*u, 8*u,0xFFCDF5A2);
        label(canvas,"SOUND, UNLOCKED.",22*u,h-19*u,10*u,0xFF332A48,true);
        label(canvas,"VOL. 01",w-67*u,h-19*u,9*u,0xFF332A48,false);
        canvas.restore();
    }

    private void label(Canvas c, String text, float x, float y, float size, int color, boolean bold) {
        paint.setColor(color); paint.setTextSize(size);
        paint.setTypeface(Typeface.create("sans-serif",bold?Typeface.BOLD:Typeface.NORMAL));
        c.drawText(text,x,y,paint);
    }
    private void star(Canvas c,float x,float y,float r,int color) {
        path.reset(); path.moveTo(x,y-r); path.lineTo(x+r*.3f,y-r*.3f);
        path.lineTo(x+r,y); path.lineTo(x+r*.3f,y+r*.3f); path.lineTo(x,y+r);
        path.lineTo(x-r*.3f,y+r*.3f); path.lineTo(x-r,y); path.lineTo(x-r*.3f,y-r*.3f); path.close();
        paint.setColor(color); c.drawPath(path,paint);
    }
}
