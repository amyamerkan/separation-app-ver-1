package com.example.demucslite;

import com.example.demucslite.audio.DemoAudio;
import com.example.demucslite.audio.WavEnvelope;

import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;

import java.io.File;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.Assert.*;

public class AudioFilesTest {
    @Rule public TemporaryFolder temp=new TemporaryFolder();

    @Test public void demoCreatesFourPlayablePcmTracksWithRealWaveforms() throws Exception {
        AtomicInteger percent=new AtomicInteger();
        File[] tracks=DemoAudio.create(temp.newFolder(),percent::set,()->{});
        assertEquals(4,tracks.length);assertEquals(100,percent.get());
        for(File track:tracks) {
            assertEquals(44+22050*16*2,track.length());
            float[] envelope=WavEnvelope.read(track,128);
            assertEquals(128,envelope.length);
            float max=0;
            for(float value:envelope) { assertTrue(Float.isFinite(value));assertTrue(value>=0&&value<=1);max=Math.max(max,value); }
            assertEquals(1f,max,.0001f);
            try(RandomAccessFile in=new RandomAccessFile(track,"r")) {
                in.seek(22);assertEquals(1,Short.reverseBytes(in.readShort()));
                assertEquals(22050,Integer.reverseBytes(in.readInt()));
            }
        }
    }

    @Test public void truncatedWavIsRejectedBeforePlayback() throws Exception {
        File[] tracks=DemoAudio.create(temp.newFolder(),p->{},()->{});
        try(RandomAccessFile file=new RandomAccessFile(tracks[0],"rw")) { file.setLength(80); }
        assertThrows(IOException.class,()->WavEnvelope.read(tracks[0],128));
    }

    @Test public void cancelledDemoStopsWriting() throws Exception {
        AtomicInteger checks=new AtomicInteger();
        assertThrows(IOException.class,()->DemoAudio.create(temp.newFolder(),p->{},()-> {
            if(checks.incrementAndGet()>3) throw new IOException("cancelled");
        }));
        assertEquals(4,checks.get());
    }
}
