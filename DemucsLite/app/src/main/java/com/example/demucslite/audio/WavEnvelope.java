package com.example.demucslite.audio;

import java.io.File;
import java.io.IOException;
import java.io.RandomAccessFile;

public final class WavEnvelope {
    private WavEnvelope() { }
    public static float[] read(File file,int bins) throws IOException {
        float[] values=new float[bins];
        try(RandomAccessFile in=new RandomAccessFile(file,"r")) {
            if(in.length()<44) throw new IOException("File WAV quá ngắn.");
            // Read chunks explicitly: a WAV can contain metadata before its PCM data.
            byte[] tag=new byte[4];in.readFully(tag);
            if(!"RIFF".equals(new String(tag,java.nio.charset.StandardCharsets.US_ASCII))) throw new IOException("File WAV không hợp lệ.");
            in.seek(8);in.readFully(tag);
            if(!"WAVE".equals(new String(tag,java.nio.charset.StandardCharsets.US_ASCII))) throw new IOException("Không đọc được âm thanh WAV.");
            int format=0,bits=0,channels=0;long dataOffset=0,dataLength=0;
            while(in.getFilePointer()+8<=in.length()) {
                in.readFully(tag);String chunk=new String(tag,java.nio.charset.StandardCharsets.US_ASCII);
                long length=Integer.toUnsignedLong(Integer.reverseBytes(in.readInt()));
                long next=in.getFilePointer()+length+(length&1);
                if(next>in.length()+1) throw new IOException("File WAV tải về chưa đầy đủ.");
                if("fmt ".equals(chunk)&&length>=16) {
                    format=Short.toUnsignedInt(Short.reverseBytes(in.readShort()));
                    channels=Short.toUnsignedInt(Short.reverseBytes(in.readShort()));
                    in.skipBytes(10);bits=Short.toUnsignedInt(Short.reverseBytes(in.readShort()));
                } else if("data".equals(chunk)) { dataOffset=in.getFilePointer();dataLength=length;break; }
                in.seek(next);
            }
            if(dataLength==0||channels==0) throw new IOException("Track âm thanh đang trống.");
            // The backend emits PCM16. Other valid encodings may still play, without a waveform.
            if(format!=1||bits!=16) return values;
            long samples=dataLength/2;float peak=0;
            for(int bin=0;bin<bins;bin++) {
                long start=samples*bin/bins,end=samples*(bin+1)/bins;
                int count=(int)Math.min(256,end-start);double square=0;
                for(int j=0;j<count;j++) {
                    long index=start+(end-start)*j/Math.max(1,count);
                    in.seek(dataOffset+index*2);
                    float sample=Short.reverseBytes(in.readShort())/32768f;square+=sample*sample;
                }
                values[bin]=(float)Math.sqrt(square/Math.max(1,count));peak=Math.max(peak,values[bin]);
            }
            if(peak>0) for(int i=0;i<bins;i++) values[i]/=peak;
        }
        return values;
    }
}
