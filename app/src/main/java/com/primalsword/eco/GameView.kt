package com.primalsword.eco

import android.content.Context
import android.graphics.*
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.view.MotionEvent
import android.view.View
import kotlin.math.*
import kotlin.random.Random

data class Enemy(var x:Float,var y:Float,var hp:Float,var speed:Float,var r:Float,var boss:Boolean=false)
data class Bullet(var x:Float,var y:Float,var vx:Float,var vy:Float,var damage:Float,var life:Float=2f,var echo:Boolean=false)
data class Gem(var x:Float,var y:Float,var value:Int)
data class Particle(var x:Float,var y:Float,var vx:Float,var vy:Float,var life:Float,var size:Float,var color:Int)
data class Echo(var angle:Float,var fire:Float)

class GameView(context: Context): View(context){
    private val p=Paint(Paint.ANTI_ALIAS_FLAG)
    private val prefs=context.getSharedPreferences("eco_arena",Context.MODE_PRIVATE)
    private val tone=ToneGenerator(AudioManager.STREAM_MUSIC,32)
    private val vibrator=context.getSystemService(Vibrator::class.java)
    private val enemies=mutableListOf<Enemy>()
    private val bullets=mutableListOf<Bullet>()
    private val gems=mutableListOf<Gem>()
    private val particles=mutableListOf<Particle>()
    private val echoes=mutableListOf<Echo>()

    private var state=0 // 0 menu 1 playing 2 levelup 3 dead
    private var px=0f; private var py=0f
    private var hp=100f; private var maxHp=100f
    private var xp=0; private var nextXp=8; private var level=1
    private var kills=0; private var time=0f; private var best=prefs.getInt("best",0)
    private var damage=18f; private var fireRate=.52f; private var fireTimer=0f
    private var moveSpeed=0f; private var bulletSpeed=0f; private var magnet=0f
    private var multishot=1; private var pierce=0; private var shield=0f
    private var spawnTimer=0f; private var bossTimer=45f; private var echoTimer=18f
    private var beat=.0f; private var combo=0; private var comboTimer=0f
    private var joyX=0f; private var joyY=0f; private var touchX=0f; private var touchY=0f; private var touching=false
    private var last=System.nanoTime()
    private var choices=listOf<Int>()

    init{ keepScreenOn=true; p.typeface=Typeface.create("sans",Typeface.BOLD) }
    override fun onAttachedToWindow(){super.onAttachedToWindow();postInvalidateOnAnimation()}

    override fun onTouchEvent(e:MotionEvent):Boolean{
        when(e.actionMasked){
            MotionEvent.ACTION_DOWN->{
                if(state==0||state==3){startGame();return true}
                if(state==2){ pickUpgrade((e.x/(width/3f)).toInt().coerceIn(0,2));return true }
                touching=true;touchX=e.x;touchY=e.y
            }
            MotionEvent.ACTION_MOVE->{touchX=e.x;touchY=e.y}
            MotionEvent.ACTION_UP,MotionEvent.ACTION_CANCEL->{touching=false;joyX=0f;joyY=0f}
        };return true
    }

    private fun startGame(){
        state=1; enemies.clear();bullets.clear();gems.clear();particles.clear();echoes.clear()
        px=width/2f;py=height*.58f;maxHp=100f;hp=maxHp;xp=0;nextXp=8;level=1;kills=0;time=0f
        damage=18f;fireRate=.52f;fireTimer=0f;moveSpeed=width*.72f;bulletSpeed=width*1.45f;magnet=width*.13f
        multishot=1;pierce=0;shield=0f;spawnTimer=.2f;bossTimer=45f;echoTimer=18f;combo=0;comboTimer=0f
        tone.startTone(ToneGenerator.TONE_PROP_BEEP,90)
    }

    override fun onDraw(c:Canvas){
        val now=System.nanoTime();val dt=min(.033f,(now-last)/1_000_000_000f);last=now
        if(state==1)update(dt)
        drawBg(c)
        when(state){0->drawMenu(c);1->drawGame(c);2->{drawGame(c);drawUpgrade(c)};3->{drawGame(c);drawDead(c)}}
        postInvalidateOnAnimation()
    }

    private fun update(dt:Float){
        time+=dt;beat-=dt;comboTimer-=dt;if(comboTimer<=0f)combo=0
        if(beat<=0f){
            val t=if((time*2).toInt()%4==0)ToneGenerator.TONE_PROP_ACK else ToneGenerator.TONE_PROP_BEEP
            tone.startTone(t,28);beat=max(.22f,.48f-time/500f)
        }
        updateInput(dt);updateSpawns(dt);updateShooting(dt);updateEnemies(dt);updateBullets(dt);updateGems(dt);updateParticles(dt);updateEchoes(dt)
        if(hp<=0f)die()
    }

    private fun updateInput(dt:Float){
        if(touching){
            val dx=touchX-px;val dy=touchY-py;val d=hypot(dx.toDouble(),dy.toDouble()).toFloat()
            if(d>8f){joyX=dx/d;joyY=dy/d}else{joyX=0f;joyY=0f}
        }
        px=(px+joyX*moveSpeed*dt).coerceIn(width*.055f,width*.945f)
        py=(py+joyY*moveSpeed*dt).coerceIn(height*.12f,height*.93f)
    }

    private fun updateSpawns(dt:Float){
        spawnTimer-=dt;bossTimer-=dt;echoTimer-=dt
        if(spawnTimer<=0f){
            val count=1+(time/35f).toInt().coerceAtMost(3);repeat(count){spawnEnemy(false)}
            spawnTimer=max(.18f,.72f-time/180f)
        }
        if(bossTimer<=0f){spawnEnemy(true);bossTimer=55f}
        if(echoTimer<=0f){echoes+=Echo(Random.nextFloat()*6.28f,.2f);echoTimer=max(12f,20f-echoes.size*1.2f);safeVibrate(80,120)}
    }

    private fun spawnEnemy(boss:Boolean){
        val edge=Random.nextInt(4);var x=0f;var y=0f
        when(edge){0->{x=-40f;y=Random.nextFloat()*height};1->{x=width+40f;y=Random.nextFloat()*height};2->{x=Random.nextFloat()*width;y=-40f};else->{x=Random.nextFloat()*width;y=height+40f}}
        val scale=1f+time/110f
        enemies+=if(boss) Enemy(x,y,420f*scale,width*.10f,width*.085f,true)
        else Enemy(x,y,(24f+time*.22f)*scale,width*(.16f+Random.nextFloat()*.10f),width*(.026f+Random.nextFloat()*.018f))
    }

    private fun updateShooting(dt:Float){
        fireTimer-=dt;if(fireTimer>0f||enemies.isEmpty())return
        val target=enemies.minByOrNull{dist(px,py,it.x,it.y)}?:return
        val a=atan2(target.y-py,target.x-px)
        val spread=.16f
        repeat(multishot){i->
            val off=(i-(multishot-1)/2f)*spread
            bullets+=Bullet(px,py,cos(a+off)*bulletSpeed,sin(a+off)*bulletSpeed,damage)
        }
        fireTimer=fireRate
    }

    private fun updateEchoes(dt:Float){
        echoes.forEachIndexed{i,e->
            e.angle+=dt*(.7f+i*.08f);e.fire-=dt
            if(e.fire<=0f&&enemies.isNotEmpty()){
                val ex=px+cos(e.angle)*width*(.10f+i*.018f);val ey=py+sin(e.angle)*width*(.10f+i*.018f)
                val t=enemies.minByOrNull{dist(ex,ey,it.x,it.y)}!!;val a=atan2(t.y-ey,t.x-ex)
                bullets+=Bullet(ex,ey,cos(a)*bulletSpeed*.9f,sin(a)*bulletSpeed*.9f,damage*.55f,2f,true)
                e.fire=max(.20f,fireRate*.78f)
            }
        }
    }

    private fun updateEnemies(dt:Float){
        for(e in enemies.toList()){
            val dx=px-e.x;val dy=py-e.y;val d=max(1f,hypot(dx.toDouble(),dy.toDouble()).toFloat())
            e.x+=dx/d*e.speed*dt;e.y+=dy/d*e.speed*dt
            if(d<e.r+width*.035f){
                val hit=max(0f,(if(e.boss)34f else 15f)-shield)
                hp-=hit*dt*2.4f;e.x-=dx/d*30f;e.y-=dy/d*30f;safeVibrate(18,55)
            }
        }
    }

    private fun updateBullets(dt:Float){
        for(b in bullets.toList()){
            b.x+=b.vx*dt;b.y+=b.vy*dt;b.life-=dt
            for(e in enemies.toList()) if(dist(b.x,b.y,e.x,e.y)<e.r+width*.012f){
                e.hp-=b.damage;burst(b.x,b.y,if(b.echo)Color.rgb(196,92,255) else Color.rgb(88,230,255),4)
                if(e.hp<=0f){
                    enemies.remove(e);kills++;combo++;comboTimer=2.3f
                    gems+=Gem(e.x,e.y,if(e.boss)8 else 1);burst(e.x,e.y,if(e.boss)Color.rgb(255,190,70) else Color.rgb(255,80,130),if(e.boss)28 else 10)
                    if(e.boss){tone.startTone(ToneGenerator.TONE_CDMA_ALERT_CALL_GUARD,260);safeVibrate(140,180)}
                }
                b.damage*=.65f
                if(pierce<=0||b.damage<3f){bullets.remove(b);break}
            }
            if(b.life<=0f||b.x<-80||b.x>width+80||b.y<-80||b.y>height+80)bullets.remove(b)
        }
    }

    private fun updateGems(dt:Float){
        for(g in gems.toList()){
            val d=dist(px,py,g.x,g.y)
            if(d<magnet){val s=width*(.55f+magnet/max(1f,d));g.x+=(px-g.x)/max(1f,d)*s*dt;g.y+=(py-g.y)/max(1f,d)*s*dt}
            if(d<width*.045f){xp+=g.value;gems.remove(g);tone.startTone(ToneGenerator.TONE_PROP_ACK,22);if(xp>=nextXp)levelUp()}
        }
    }

    private fun levelUp(){xp-=nextXp;level++;nextXp=(nextXp*1.34f+3).toInt();state=2;choices=(0..8).shuffled().take(3);safeVibrate(70,110)}
    private fun pickUpgrade(index:Int){
        when(choices[index]){
            0->{damage*=1.28f}
            1->{fireRate=max(.12f,fireRate*.82f)}
            2->{moveSpeed*=1.18f}
            3->{multishot=(multishot+1).coerceAtMost(6)}
            4->{maxHp+=28f;hp+=28f}
            5->{magnet*=1.45f}
            6->{pierce++}
            7->{shield+=2.5f}
            8->{echoes+=Echo(Random.nextFloat()*6.28f,.1f)}
        };state=1;tone.startTone(ToneGenerator.TONE_PROP_BEEP2,100)
    }

    private fun die(){state=3;best=max(best,time.toInt());prefs.edit().putInt("best",best).apply();tone.startTone(ToneGenerator.TONE_PROP_NACK,250);safeVibrate(180,200)}
    private fun updateParticles(dt:Float){particles.forEach{it.x+=it.vx*dt;it.y+=it.vy*dt;it.vx*=.96f;it.vy*=.96f;it.life-=dt};particles.removeAll{it.life<=0f}}
    private fun burst(x:Float,y:Float,color:Int,n:Int){repeat(n){val a=Random.nextFloat()*6.28f;val s=Random.nextFloat()*width*.38f;particles+=Particle(x,y,cos(a)*s,sin(a)*s,.25f+Random.nextFloat()*.45f,2f+Random.nextFloat()*6f,color)}}
    private fun safeVibrate(ms:Long,amp:Int){try{if(Build.VERSION.SDK_INT>=26)vibrator?.vibrate(VibrationEffect.createOneShot(ms,amp))else @Suppress("DEPRECATION") vibrator?.vibrate(ms)}catch(_:Exception){}}
    private fun dist(x1:Float,y1:Float,x2:Float,y2:Float)=hypot((x1-x2).toDouble(),(y1-y2).toDouble()).toFloat()

    private fun drawBg(c:Canvas){
        c.drawColor(Color.rgb(4,6,18));p.strokeWidth=1f
        val off=(time*24f)%80f
        for(i in -1..20){p.color=Color.argb(22,70,130,255);val y=i*80f+off;c.drawLine(0f,y,width.toFloat(),y-100f,p)}
        for(i in 0..9){p.color=Color.argb(14,196,92,255);val x=i*width/9f;c.drawLine(x,0f,x+80f,height.toFloat(),p)}
    }

    private fun drawMenu(c:Canvas){
        text(c,"ECO",height*.18f,width*.19f,Color.WHITE);text(c,"RUPTURA",height*.26f,width*.075f,Color.rgb(88,230,255))
        text(c,"VOCÊ NÃO SOBREVIVE SOZINHA",height*.33f,width*.032f,Color.LTGRAY)
        p.style=Paint.Style.STROKE;p.strokeWidth=width*.018f;p.color=Color.rgb(196,92,255);c.drawCircle(width/2f,height*.51f,width*.14f,p)
        p.color=Color.rgb(88,230,255);c.drawCircle(width/2f,height*.51f,width*.075f,p);p.style=Paint.Style.FILL
        text(c,"TOQUE PARA ROMPER O CICLO",height*.72f,width*.049f,Color.WHITE)
        text(c,"arraste para mover • ataque automático",height*.77f,width*.030f,Color.GRAY)
        text(c,"RECORDE  ${best}s",height*.88f,width*.038f,Color.rgb(196,92,255))
    }

    private fun drawGame(c:Canvas){
        gems.forEach{p.color=Color.rgb(90,255,180);c.drawCircle(it.x,it.y,width*.012f+it.value*1.2f,p)}
        enemies.forEach{e->
            p.color=if(e.boss)Color.rgb(255,170,60) else Color.rgb(255,70,120);c.drawCircle(e.x,e.y,e.r,p)
            if(e.boss){p.style=Paint.Style.STROKE;p.strokeWidth=6f;p.color=Color.WHITE;c.drawCircle(e.x,e.y,e.r*1.25f,p);p.style=Paint.Style.FILL}
        }
        bullets.forEach{p.color=if(it.echo)Color.rgb(196,92,255) else Color.rgb(88,230,255);c.drawCircle(it.x,it.y,width*.010f,p)}
        echoes.forEachIndexed{i,e->val ex=px+cos(e.angle)*width*(.10f+i*.018f);val ey=py+sin(e.angle)*width*(.10f+i*.018f);p.color=Color.argb(180,196,92,255);c.drawCircle(ex,ey,width*.024f,p)}
        p.color=Color.WHITE;c.drawCircle(px,py,width*.038f,p);p.color=Color.rgb(88,230,255);c.drawCircle(px,py,width*.020f,p)
        particles.forEach{p.color=Color.argb((it.life*350).toInt().coerceIn(0,255),Color.red(it.color),Color.green(it.color),Color.blue(it.color));c.drawCircle(it.x,it.y,it.size,p)}
        drawHud(c)
    }

    private fun drawHud(c:Canvas){
        p.color=Color.argb(180,10,14,34);c.drawRect(0f,0f,width.toFloat(),height*.115f,p)
        p.color=Color.rgb(45,55,90);c.drawRoundRect(width*.05f,height*.028f,width*.95f,height*.050f,20f,20f,p)
        p.color=Color.rgb(90,255,170);c.drawRoundRect(width*.05f,height*.028f,width*(.05f+.90f*hp/maxHp),height*.050f,20f,20f,p)
        p.color=Color.rgb(40,46,75);c.drawRoundRect(width*.05f,height*.070f,width*.95f,height*.087f,20f,20f,p)
        p.color=Color.rgb(196,92,255);c.drawRoundRect(width*.05f,height*.070f,width*(.05f+.90f*xp/max(1f,nextXp.toFloat())),height*.087f,20f,20f,p)
        text(c,"NÍVEL $level   •   ${time.toInt()}s   •   $kills ABATES",height*.108f,width*.029f,Color.WHITE)
        if(combo>=3)text(c,"COMBO x$combo",height*.16f,width*.050f,Color.rgb(255,190,70))
        val boss=max(0,bossTimer.toInt());text(c,"CHEFE EM ${boss}s",height*.96f,width*.030f,Color.LTGRAY)
    }

    private fun drawUpgrade(c:Canvas){
        p.color=Color.argb(230,2,4,14);c.drawRect(0f,0f,width.toFloat(),height.toFloat(),p)
        text(c,"RUPTURA EVOLUTIVA",height*.20f,width*.060f,Color.WHITE);text(c,"ESCOLHA UMA MUTAÇÃO",height*.26f,width*.034f,Color.rgb(88,230,255))
        for(i in 0..2){val l=i*width/3f+width*.025f;val r=(i+1)*width/3f-width*.025f;p.color=Color.rgb(18,26,55);c.drawRoundRect(l,height*.38f,r,height*.72f,28f,28f,p);p.style=Paint.Style.STROKE;p.strokeWidth=4f;p.color=if(i==1)Color.rgb(196,92,255) else Color.rgb(88,230,255);c.drawRoundRect(l,height*.38f,r,height*.72f,28f,28f,p);p.style=Paint.Style.FILL
            textAt(c,upgradeTitle(choices[i]),(l+r)/2,height*.49f,width*.032f,Color.WHITE);textAt(c,upgradeDesc(choices[i]),(l+r)/2,height*.59f,width*.023f,Color.LTGRAY)
        }
    }
    private fun upgradeTitle(i:Int)=arrayOf("DANO","CADÊNCIA","VELOCIDADE","MULTIDISPARO","VITALIDADE","ÍMÃ","PERFURAÇÃO","BLINDAGEM","NOVO ECO")[i]
    private fun upgradeDesc(i:Int)=arrayOf("+28% poder","atira mais rápido","movimento +18%","mais um projétil","+28 de vida","coleta distante","atravessa alvos","reduz dano","aliado orbital")[i]

    private fun drawDead(c:Canvas){p.color=Color.argb(225,2,3,12);c.drawRect(0f,0f,width.toFloat(),height.toFloat(),p);text(c,"RUPTURA COLAPSADA",height*.38f,width*.064f,Color.WHITE);text(c,"${time.toInt()} SEGUNDOS",height*.49f,width*.105f,Color.rgb(88,230,255));text(c,"$kills ABATES  •  NÍVEL $level",height*.57f,width*.036f,Color.LTGRAY);text(c,"TOQUE PARA TENTAR OUTRA BUILD",height*.72f,width*.041f,Color.WHITE)}
    private fun text(c:Canvas,s:String,y:Float,size:Float,color:Int){textAt(c,s,width/2f,y,size,color)}
    private fun textAt(c:Canvas,s:String,x:Float,y:Float,size:Float,color:Int){p.textAlign=Paint.Align.CENTER;p.textSize=size;p.color=color;c.drawText(s,x,y,p)}
}
