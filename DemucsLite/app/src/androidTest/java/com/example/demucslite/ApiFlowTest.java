package com.example.demucslite;

import android.content.Context;
import android.net.Uri;
import android.os.SystemClock;
import android.view.View;

import androidx.lifecycle.ViewModelProvider;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import com.example.demucslite.audio.DemoAudio;

import org.junit.Test;
import org.junit.runner.RunWith;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.Assert.*;

/** Real HTTP/multipart/status/cache integration against an isolated device-local fixture. */
@RunWith(AndroidJUnit4.class)
public class ApiFlowTest {
    @Test public void multipartUploadPollsActualStatusAndDownloadsAllFourStems() throws Exception {
        Context app=InstrumentationRegistry.getInstrumentation().getTargetContext();
        File folder=new File(app.getCacheDir(),"api_fixture_"+System.nanoTime());assertTrue(folder.mkdirs());
        File[] wavs=DemoAudio.create(folder,p->{},()->{});
        try(Fixture server=new Fixture(wavs);
            ActivityScenario<MainActivity> scenario=ActivityScenario.launch(MainActivity.class)) {
            AtomicBoolean ready=new AtomicBoolean(),sawProcessing=new AtomicBoolean();
            scenario.onActivity(activity -> {
                StudioSession session=new ViewModelProvider(activity).get(StudioSession.class);
                session.changes.observe(activity,state -> {
                    if(state.phase==StudioSession.Phase.SEPARATING) {
                        sawProcessing.set(true);assertEquals(-1,state.progress);
                    }
                });
                activity.findViewById(R.id.btnStart).performClick();
                session.serverUrl="http://127.0.0.1:"+server.socket.getLocalPort();
                session.select(Uri.fromFile(wavs[0]),"test-input.wav",wavs[0].length());
                activity.findViewById(R.id.btnSeparate).performClick();
            });
            long deadline=SystemClock.uptimeMillis()+25000;
            while(!ready.get()&&SystemClock.uptimeMillis()<deadline) {
                scenario.onActivity(activity -> {
                    StudioSession state=new ViewModelProvider(activity).get(StudioSession.class);
                    if(state.phase==StudioSession.Phase.ERROR) fail(state.error);
                    ready.set(state.phase==StudioSession.Phase.READY
                            &&activity.findViewById(R.id.screenMixer).getVisibility()==View.VISIBLE);
                });
                SystemClock.sleep(100);
            }
            assertTrue("Processing status should remain indeterminate without server percentages",sawProcessing.get());
            assertTrue("Successful API job should open mixer",ready.get());
            assertTrue("Multipart body should contain audio",server.uploadBytes.get()>wavs[0].length());
            assertEquals(4,server.downloads.get());
            scenario.onActivity(activity -> {
                StudioSession state=new ViewModelProvider(activity).get(StudioSession.class);
                assertFalse(state.demo);assertEquals(4,state.stems.length);
                for(StudioSession.Stem stem:state.stems) assertTrue(stem.file.length()>44);
            });
        }
    }

    private static class Fixture implements AutoCloseable {
        final ServerSocket socket;
        final AtomicInteger uploadBytes=new AtomicInteger(),downloads=new AtomicInteger(),polls=new AtomicInteger();
        volatile boolean closed;
        Fixture(File[] wavs) throws Exception {
            socket=new ServerSocket(0,8,InetAddress.getByName("127.0.0.1"));
            Thread thread=new Thread(()-> {
                while(!closed) {
                    try(Socket client=socket.accept()) {
                        client.setSoTimeout(10000);InputStream in=client.getInputStream();
                        ByteArrayOutputStream header=new ByteArrayOutputStream();int b;
                        while((b=in.read())!=-1) {
                            header.write(b);byte[] data=header.toByteArray();int n=data.length;
                            if(n>=4&&data[n-4]==13&&data[n-3]==10&&data[n-2]==13&&data[n-1]==10) break;
                            if(n>65536) throw new IllegalStateException("Headers too large");
                        }
                        String headers=header.toString(StandardCharsets.US_ASCII.name());
                        String route=headers.split(" ")[1];int length=0;
                        for(String line:headers.split("\r\n")) if(line.toLowerCase(java.util.Locale.ROOT).startsWith("content-length:")) length=Integer.parseInt(line.substring(15).trim());
                        int consumed=0;byte[] buffer=new byte[65536];
                        while(consumed<length) { int n=in.read(buffer,0,Math.min(buffer.length,length-consumed));if(n<0) break;consumed+=n; }
                        byte[] body;String mime="application/json";
                        if(route.equals("/separate")) {
                            uploadBytes.set(consumed);body="{\"job_id\":\"fixture\",\"status\":\"pending\"}".getBytes(StandardCharsets.UTF_8);
                        } else if(route.startsWith("/status/")) {
                            if(polls.incrementAndGet()==1) body="{\"status\":\"processing\"}".getBytes(StandardCharsets.UTF_8);
                            else {
                                StringBuilder json=new StringBuilder("{\"status\":\"done\",\"result_urls\":{");
                                for(int i=0;i<4;i++) {
                                    if(i>0) json.append(',');
                                    json.append('"').append(StudioSession.KEYS[i]).append("\":\"http://localhost:")
                                            .append(socket.getLocalPort()).append("/files/").append(i).append(".wav\"");
                                }
                                body=json.append("}}").toString().getBytes(StandardCharsets.UTF_8);
                            }
                        } else {
                            int index=Integer.parseInt(route.substring(route.lastIndexOf('/')+1,route.lastIndexOf('.')));
                            body=Files.readAllBytes(wavs[index].toPath());downloads.incrementAndGet();mime="audio/wav";
                        }
                        OutputStream out=client.getOutputStream();
                        out.write(("HTTP/1.1 200 OK\r\nContent-Type: "+mime+"\r\nContent-Length: "+body.length+"\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
                        out.write(body);out.flush();
                    } catch(Exception e) { if(!closed) throw new RuntimeException(e); }
                }
            },"studio-api-fixture");thread.setDaemon(true);thread.start();
        }
        @Override public void close() throws Exception { closed=true;socket.close(); }
    }
}
