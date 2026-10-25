package com.example.demucslite.audio;

import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.util.Random;
import java.util.function.IntConsumer;

/** Small locally synthesized loop. This is explicitly a demo, not an AI separation result. */
public final class DemoAudio {
    private static final int RATE=22050, SECONDS=16;
    public interface Cancellation { void check() throws IOException; }
    private DemoAudio() { }
    public static File[] create(File folder,IntConsumer progress,Cancellation cancellation) throws IOException {
        File[] files=new File[4];String[] names={"vocals","drums","bass","other"};
        int frames=RATE*SECONDS;double[] melody={440,523.25,659.25,587.33,523.25,440,392,329.63};
        for(int stem=0;stem<4;stem++) {
            files[stem]=new File(folder,names[stem]+".wav");Random random=new Random(42);
            try(OutputStream out=new BufferedOutputStream(new FileOutputStream(files[stem]))) {
                out.write(new byte[]{'R','I','F','F'});le32(out,36+frames*2);out.write(new byte[]{'W','A','V','E','f','m','t',' '});
                le32(out,16);le16(out,1);le16(out,1);le32(out,RATE);le32(out,RATE*2);le16(out,2);le16(out,16);
                out.write(new byte[]{'d','a','t','a'});le32(out,frames*2);
                for(int n=0;n<frames;n++) {
                    if(n%8192==0) { cancellation.check();progress.accept((int)((stem+n/(float)frames)*25)); }
                    double t=n/(double)RATE,beat=t%.5, note=t%.25,value;
                    double fade=Math.min(1,Math.min(t/.05,(SECONDS-t)/.12));
                    if(stem==0) {
                        double f=melody[(int)(t*2)%melody.length];
                        value=.15*(Math.sin(2*Math.PI*f*t)+.3*Math.sin(2*Math.PI*f*2*t))*Math.exp(-note*6);
                    } else if(stem==1) {
                        double kick=.28*Math.sin(2*Math.PI*(52*beat+1.8*(1-Math.exp(-beat*35))))*Math.exp(-beat*19);
                        double hat=.045*(random.nextDouble()*2-1)*Math.exp(-note*75);
                        double snare=((int)(t*2)%2==1)?.12*(random.nextDouble()*2-1)*Math.exp(-beat*27):0;
                        value=kick+hat+snare;
                    } else if(stem==2) {
                        double f=new double[]{110,130.81,98,87.31}[(int)(t/2)%4];
                        value=.2*(Math.sin(2*Math.PI*f*t)+.2*Math.sin(2*Math.PI*f*2*t))*Math.exp(-beat*3);
                    } else {
                        double root=new double[]{220,261.63,196,174.61}[(int)(t/2)%4];
                        value=.065*(Math.sin(2*Math.PI*root*t)+Math.sin(2*Math.PI*root*1.25*t)+Math.sin(2*Math.PI*root*1.5*t))*(.65+.35*Math.sin(Math.PI*t));
                    }
                    le16(out,(int)(Math.max(-1,Math.min(1,value*fade))*32767));
                }
            }
            progress.accept((stem+1)*25);
        }
        return files;
    }
    private static void le16(OutputStream out,int n) throws IOException { out.write(n&255);out.write((n>>8)&255); }
    private static void le32(OutputStream out,int n) throws IOException { le16(out,n);le16(out,n>>16); }
}
