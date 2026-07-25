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

data class Enemy(var x:Float,var y:Float,var hp:Float,var maxHp:Float,var speed:Float,var r:Float,val type:Int,var phase:Float=0f,var cooldown:Float=0f)
data class Bullet(var x:Float,var y:Float,var vx:Float,var vy:Float,var damage:Float,var life:Float=2f,var hostile:Boolean=false,var pierce:Int=0)
data class Gem(var x:Float,var y:Float,var value:Int)
data class Particle(var x:Float,var y:Float,var vx:Float,var vy:Float,var life:Float,var size:Float,var color:Int)
data class Echo(var angle:Float,var fire:Float)

class GameView(context:Context):View(context){
    private val p=Paint(Paint.ANTI_ALIAS_FLAG)
    private val prefs=context.getSharedPreferences("eco_ruptura_v2",Context.MODE_PRIVATE)
    private val tone=ToneGenerator(AudioManager.STREAM_MUSIC,34)
    private val vibrator=context.getSystemService(Vibrator::class.java)
    private val enemies=mutableListOf<Enemy>()
    private val bullets=mutableListOf<Bullet>()
    private val gems=mutableListOf<Gem>()
    private val particles=mutableListOf<Particle>()
    private val echoes=mutableListOf<Echo>()

    private var state=0 // 0 menu, 1 playing, 2 upgrade, 3 dead, 4 victory
    private var px=0f; private var py=0f; private var facing=0f
    private var hp=120f; private var maxHp=120f; private var shield=0f
    private var xp=0; private var nextXp=10; private var level=1
    private var kills=0; private var collected=0; private var time=0f; private var best=prefs.getInt("best",0)
    private var damage=22f; private var fireRate=.48f; private var fireTimer=0f
    private var moveSpeed=0f; private var bulletSpeed=0f; private var magnet=0f; private var multishot=1; private var pierce=0
    private var spawnTimer=.2f; private var bossAlive=false; private var bossDefeated=false
    private var beat=.0f; private var combo=0; private var comboTimer=0f
    private var touchX=0f; private var touchY=0f; private var touching=false
    private var last=System.nanoTime(); private var choices=listOf<Int>()
    private var objective=0; private var objectiveProgress=0; private var objectiveTarget=20; private var objectiveReward=1

    init{keepScreenOn=true;p.typeface=Typeface.create("sans",Typeface.BOLD)}
    override fun onAttachedToWindow(){super.onAttachedToWindow();postInvalidateOnAnimation()}

    override fun onTouchEvent(e:MotionEvent):Boolean{
        when(e.actionMasked){
            MotionEvent.ACTION_DOWN->{
                if(state==0||state==3||state==4){startGame();return true}
                if(state==2){pickUpgrade((e.x/(width/3f)).toInt().coerceIn(0,2));return true}
                touching=true;touchX=e.x;touchY=e.y
            }
            MotionEvent.ACTION_MOVE->{touchX=e.x;touchY=e.y}
            MotionEvent.ACTION_UP,MotionEvent.ACTION_CANCEL->touching=false
        }
        return true
    }

    private fun startGame(){
        state=1;enemies.clear();bullets.clear();gems.clear();particles.clear();echoes.clear()
        px=width/2f;py=height*.62f;hp=120f;maxHp=120f;shield=0f;xp=0;nextXp=10;level=1;kills=0;collected=0;time=0f
        damage=22f;fireRate=.48f;fireTimer=0f;moveSpeed=width*.78f;bulletSpeed=width*1.7f;magnet=width*.17f;multishot=1;pierce=0
        spawnTimer=.2f;bossAlive=false;bossDefeated=false;combo=0;comboTimer=0f;objective=0;objectiveProgress=0;objectiveTarget=20;objectiveReward=1
        tone.startTone(ToneGenerator.TONE_PROP_BEEP,100)
    }

    override fun onDraw(c:Canvas){
        val now=System.nanoTime();val dt=min(.033f,(now-last)/1_000_000_000f);last=now
        if(state==1)update(dt)
        drawBg(c)
        when(state){0->drawMenu(c);1->drawGame(c);2->{drawGame(c);drawUpgrade(c)};3->{drawGame(c);drawDead(c)};4->{drawGame(c);drawVictory(c)}}
        postInvalidateOnAnimation()
    }

    private fun update(dt:Float){
        time+=dt;beat-=dt;comboTimer-=dt;if(comboTimer<=0f)combo=0
        if(beat<=0f){tone.startTone(if((time*2).toInt()%4==0)ToneGenerator.TONE_PROP_ACK else ToneGenerator.TONE_PROP_BEEP,24);beat=max(.20f,.46f-time/600f)}
        updateInput(dt);updateObjective(dt);updateSpawns(dt);updateShooting(dt);updateEnemies(dt);updateBullets(dt);updateGems(dt);updateParticles(dt);updateEchoes(dt)
        if(hp<=0f)die()
    }

    private fun updateInput(dt:Float){
        if(touching){val dx=touchX-px;val dy=touchY-py;val d=hypot(dx.toDouble(),dy.toDouble()).toFloat();if(d>8f){facing=atan2(dy,dx);px+=dx/d*moveSpeed*dt;py+=dy/d*moveSpeed*dt}}
        px=px.coerceIn(width*.06f,width*.94f);py=py.coerceIn(height*.13f,height*.93f)
    }

    private fun updateObjective(dt:Float){
        when(objective){
            0->{objectiveProgress=kills;if(objectiveProgress>=objectiveTarget)advanceObjective()}
            1->{objectiveProgress=collected;if(objectiveProgress>=objectiveTarget)advanceObjective()}
            2->{objectiveProgress=time.toInt();if(time>=objectiveTarget)advanceObjective()}
            3->{objectiveProgress=if(bossDefeated)1 else 0;if(bossDefeated)advanceObjective()}
            4->{objectiveProgress=time.toInt();if(time>=objectiveTarget){state=4;best=max(best,time.toInt());prefs.edit().putInt("best",best).apply()}}
        }
    }

    private fun advanceObjective(){
        objective++;objectiveProgress=0;objectiveReward++
        when(objective){1->objectiveTarget=35;2->objectiveTarget=75;3->{objectiveTarget=1;spawnBoss()};4->objectiveTarget=120}
        hp=min(maxHp,hp+28f);xp+=5;echoes+=Echo(Random.nextFloat()*TAU,.1f);burst(px,py,Color.rgb(110,255,160),24);safeVibrate(100,150)
    }

    private fun updateSpawns(dt:Float){
        spawnTimer-=dt
        if(spawnTimer<=0f){repeat(1+(time/45f).toInt().coerceAtMost(3)){spawnEnemy()};spawnTimer=max(.16f,.68f-time/220f)}
    }

    private fun spawnEnemy(){
        val edge=Random.nextInt(4);val pos=when(edge){0->-60f to Random.nextFloat()*height;1->width+60f to Random.nextFloat()*height;2->Random.nextFloat()*width to -60f;else->Random.nextFloat()*width to height+60f}
        val roll=Random.nextFloat();val type=when{time>70f&&roll<.12f->3;time>35f&&roll<.30f->2;time>15f&&roll<.55f->1;else->0}
        val base=when(type){0->34f;1->52f;2->44f;else->120f};val r=when(type){0->width*.034f;1->width*.046f;2->width*.041f;else->width*.066f}
        val speed=when(type){0->width*.27f;1->width*.18f;2->width*.22f;else->width*.11f}
        val hpv=base*(1f+time/100f);enemies+=Enemy(pos.first,pos.second,hpv,hpv,speed,r,type,Random.nextFloat()*TAU,Random.nextFloat())
    }

    private fun spawnBoss(){
        if(bossAlive)return;bossAlive=true;val hpv=1100f+time*8f;enemies+=Enemy(width/2f,-width*.12f,hpv,hpv,width*.10f,width*.12f,4,0f,1f);tone.startTone(ToneGenerator.TONE_CDMA_ALERT_CALL_GUARD,400);safeVibrate(180,220)
    }

    private fun updateShooting(dt:Float){
        fireTimer-=dt;if(fireTimer>0f||enemies.isEmpty())return
        val t=enemies.minByOrNull{dist(px,py,it.x,it.y)}?:return;val a=atan2(t.y-py,t.x-px);facing=a
        repeat(multishot){i->val off=(i-(multishot-1)/2f)*.13f;bullets+=Bullet(px+cos(a)*width*.05f,py+sin(a)*width*.05f,cos(a+off)*bulletSpeed,sin(a+off)*bulletSpeed,damage,2f,false,pierce)}
        fireTimer=fireRate
    }

    private fun updateEchoes(dt:Float){
        echoes.forEachIndexed{i,e->e.angle+=dt*(.8f+i*.06f);e.fire-=dt;if(e.fire<=0f&&enemies.isNotEmpty()){
            val ex=px+cos(e.angle)*width*(.12f+i*.015f);val ey=py+sin(e.angle)*width*(.12f+i*.015f);val t=enemies.minByOrNull{dist(ex,ey,it.x,it.y)}!!;val a=atan2(t.y-ey,t.x-ex)
            bullets+=Bullet(ex,ey,cos(a)*bulletSpeed*.85f,sin(a)*bulletSpeed*.85f,damage*.48f,2f,false,0);e.fire=max(.18f,fireRate*.72f)
        }}
    }

    private fun updateEnemies(dt:Float){
        for(e in enemies.toList()){
            e.phase+=dt;e.cooldown-=dt;val dx=px-e.x;val dy=py-e.y;val d=max(1f,hypot(dx.toDouble(),dy.toDouble()).toFloat())
            when(e.type){
                0->{e.x+=dx/d*e.speed*dt;e.y+=dy/d*e.speed*dt}
                1->{val sway=sin(e.phase*5f)*width*.08f;e.x+=(dx/d*e.speed-dy/d*sway)*dt;e.y+=(dy/d*e.speed+dx/d*sway)*dt}
                2->{if(e.cooldown<=0f){e.x+=dx/d*width*.18f;e.y+=dy/d*width*.18f;e.cooldown=.8f};e.x+=dx/d*e.speed*.35f*dt;e.y+=dy/d*e.speed*.35f*dt}
                3->{e.x+=dx/d*e.speed*dt;e.y+=dy/d*e.speed*dt;if(e.cooldown<=0f){enemyBurst(e,6);e.cooldown=2.2f}}
                4->{e.x+=dx/d*e.speed*dt;e.y+=dy/d*e.speed*dt;if(e.cooldown<=0f){enemyBurst(e,12);e.cooldown=1.25f}}
            }
            if(d<e.r+width*.035f){hp-=max(0f,(when(e.type){4->42f;3->24f;else->14f})-shield)*dt*2.1f;safeVibrate(15,45)}
        }
    }

    private fun enemyBurst(e:Enemy,count:Int){repeat(count){i->val a=TAU*i/count+e.phase;bullets+=Bullet(e.x,e.y,cos(a)*width*.42f,sin(a)*width*.42f,10f,3f,true,0)}}

    private fun updateBullets(dt:Float){
        for(b in bullets.toList()){
            b.x+=b.vx*dt;b.y+=b.vy*dt;b.life-=dt
            if(b.hostile){if(dist(b.x,b.y,px,py)<width*.045f){hp-=b.damage;bullets.remove(b);burst(px,py,Color.rgb(255,90,120),8);safeVibrate(22,75)}}
            else for(e in enemies.toList())if(dist(b.x,b.y,e.x,e.y)<e.r+width*.012f){
                e.hp-=b.damage;burst(b.x,b.y,Color.rgb(88,230,255),4)
                if(e.hp<=0f){enemies.remove(e);kills++;combo++;comboTimer=2.4f;val value=when(e.type){4->20;3->5;else->1};gems+=Gem(e.x,e.y,value);burst(e.x,e.y,enemyColor(e.type),if(e.type==4)42 else 12)
                    if(e.type==4){bossAlive=false;bossDefeated=true;tone.startTone(ToneGenerator.TONE_CDMA_ALERT_CALL_GUARD,500);safeVibrate(220,255)}}
                if(b.pierce>0)b.pierce-- else {bullets.remove(b);break}
            }
            if(b.life<=0f||b.x<-100||b.x>width+100||b.y<-100||b.y>height+100)bullets.remove(b)
        }
    }

    private fun updateGems(dt:Float){for(g in gems.toList()){val d=dist(px,py,g.x,g.y);if(d<magnet){val s=width*(.65f+magnet/max(1f,d));g.x+=(px-g.x)/max(1f,d)*s*dt;g.y+=(py-g.y)/max(1f,d)*s*dt};if(d<width*.05f){xp+=g.value;collected+=g.value;gems.remove(g);if(xp>=nextXp)levelUp()}}}
    private fun levelUp(){xp-=nextXp;level++;nextXp=(nextXp*1.32f+4).toInt();state=2;choices=(0..8).shuffled().take(3);safeVibrate(70,110)}
    private fun pickUpgrade(index:Int){when(choices[index]){0->damage*=1.3f;1->fireRate=max(.10f,fireRate*.82f);2->moveSpeed*=1.2f;3->multishot=(multishot+1).coerceAtMost(7);4->{maxHp+=30f;hp+=30f};5->magnet*=1.45f;6->pierce++;7->shield+=3f;8->echoes+=Echo(Random.nextFloat()*TAU,.1f)};state=1;tone.startTone(ToneGenerator.TONE_PROP_BEEP2,110)}
    private fun die(){state=3;best=max(best,time.toInt());prefs.edit().putInt("best",best).apply();tone.startTone(ToneGenerator.TONE_PROP_NACK,280);safeVibrate(190,220)}
    private fun updateParticles(dt:Float){particles.forEach{it.x+=it.vx*dt;it.y+=it.vy*dt;it.vx*=.95f;it.vy*=.95f;it.life-=dt};particles.removeAll{it.life<=0f}}
    private fun burst(x:Float,y:Float,color:Int,n:Int){repeat(n){val a=Random.nextFloat()*TAU;val s=Random.nextFloat()*width*.42f;particles+=Particle(x,y,cos(a)*s,sin(a)*s,.28f+Random.nextFloat()*.5f,2f+Random.nextFloat()*7f,color)}}
    private fun safeVibrate(ms:Long,amp:Int){try{if(Build.VERSION.SDK_INT>=26)vibrator?.vibrate(VibrationEffect.createOneShot(ms,amp))else @Suppress("DEPRECATION") vibrator?.vibrate(ms)}catch(_:Exception){}}
    private fun dist(x1:Float,y1:Float,x2:Float,y2:Float)=hypot((x1-x2).toDouble(),(y1-y2).toDouble()).toFloat()
    private fun enemyColor(t:Int)=when(t){0->Color.rgb(255,85,120);1->Color.rgb(255,175,65);2->Color.rgb(170,90,255);3->Color.rgb(70,220,255);else->Color.rgb(255,55,80)}

    private fun drawBg(c:Canvas){c.drawColor(Color.rgb(5,7,18));val off=(time*28f)%90f;for(i in -1..20){p.color=Color.argb(20,60,125,255);c.drawLine(0f,i*90f+off,width.toFloat(),i*90f+off-110f,p)};for(i in 0..8){p.color=Color.argb(12,196,92,255);val x=i*width/8f;c.drawLine(x,0f,x+90f,height.toFloat(),p)}}
    private fun drawMenu(c:Canvas){text(c,"ECO",height*.17f,width*.19f,Color.WHITE);text(c,"RUPTURA",height*.25f,width*.078f,Color.rgb(88,230,255));text(c,"ROGUELITE DE SOBREVIVÊNCIA TEMPORAL",height*.32f,width*.031f,Color.LTGRAY);drawHero(c,width/2f,height*.51f,0f,width*.14f);text(c,"TOQUE PARA INICIAR",height*.74f,width*.052f,Color.WHITE);text(c,"cumpra objetivos • evolua • derrote o núcleo",height*.79f,width*.029f,Color.GRAY);text(c,"RECORDE  ${best}s",height*.88f,width*.039f,Color.rgb(196,92,255))}

    private fun drawGame(c:Canvas){
        gems.forEach{p.color=Color.rgb(110,255,160);c.drawDiamond(it.x,it.y,width*.018f,p)}
        bullets.forEach{p.color=if(it.hostile)Color.rgb(255,90,120) else Color.rgb(88,230,255);c.drawCircle(it.x,it.y,width*.009f,p)}
        enemies.forEach{drawEnemy(c,it)}
        echoes.forEachIndexed{i,e->val x=px+cos(e.angle)*width*(.12f+i*.015f);val y=py+sin(e.angle)*width*(.12f+i*.015f);p.color=Color.argb(180,196,92,255);c.drawCircle(x,y,width*.022f,p);p.style=Paint.Style.STROKE;p.strokeWidth=3f;c.drawCircle(x,y,width*.033f,p);p.style=Paint.Style.FILL}
        particles.forEach{p.color=Color.argb((it.life*360).toInt().coerceIn(0,255),Color.red(it.color),Color.green(it.color),Color.blue(it.color));c.drawCircle(it.x,it.y,it.size,p)}
        drawHero(c,px,py,facing,width*.075f)
        drawHud(c)
    }

    private fun drawHero(c:Canvas,x:Float,y:Float,a:Float,s:Float){
        c.save();c.rotate(Math.toDegrees(a.toDouble()).toFloat()+90f,x,y)
        val body=Path();body.moveTo(x,y-s*.72f);body.lineTo(x-s*.48f,y+s*.50f);body.lineTo(x,y+s*.28f);body.lineTo(x+s*.48f,y+s*.50f);body.close();p.color=Color.rgb(230,245,255);c.drawPath(body,p)
        p.color=Color.rgb(28,45,80);c.drawCircle(x,y-s*.18f,s*.34f,p);p.color=Color.rgb(88,230,255);c.drawRect(x-s*.25f,y-s*.23f,x+s*.25f,y-s*.11f,p)
        p.color=Color.rgb(196,92,255);c.drawRect(x-s*.10f,y+s*.20f,x+s*.10f,y+s*.78f,p);c.restore()
    }

    private fun drawEnemy(c:Canvas,e:Enemy){
        val col=enemyColor(e.type);p.color=col
        when(e.type){
            0->{val path=Path();for(i in 0..5){val a=TAU*i/6+e.phase;val r=if(i%2==0)e.r else e.r*.55f;val x=e.x+cos(a)*r;val y=e.y+sin(a)*r;if(i==0)path.moveTo(x,y)else path.lineTo(x,y)};path.close();c.drawPath(path,p);p.color=Color.WHITE;c.drawCircle(e.x,e.y,e.r*.22f,p)}
            1->{c.save();c.rotate((sin(e.phase)*18f),e.x,e.y);c.drawRoundRect(e.x-e.r,e.y-e.r*.55f,e.x+e.r,e.y+e.r*.55f,e.r*.3f,e.r*.3f,p);p.color=Color.rgb(30,20,20);c.drawRect(e.x-e.r*.55f,e.y-e.r*.12f,e.x+e.r*.55f,e.y+e.r*.12f,p);p.color=Color.WHITE;c.drawCircle(e.x+e.r*.28f,e.y-e.r*.12f,e.r*.12f,p);c.restore()}
            2->{p.style=Paint.Style.STROKE;p.strokeWidth=e.r*.22f;c.drawCircle(e.x,e.y,e.r*.75f,p);c.drawArc(e.x-e.r,e.y-e.r,e.x+e.r,e.y+e.r,e.phase*80f,210f,false,p);p.style=Paint.Style.FILL;p.color=Color.WHITE;c.drawCircle(e.x,e.y,e.r*.16f,p)}
            3->{val path=Path();path.moveTo(e.x,e.y-e.r);path.lineTo(e.x-e.r*.85f,e.y+e.r*.55f);path.lineTo(e.x-e.r*.25f,e.y+e.r*.25f);path.lineTo(e.x,e.y+e.r);path.lineTo(e.x+e.r*.25f,e.y+e.r*.25f);path.lineTo(e.x+e.r*.85f,e.y+e.r*.55f);path.close();c.drawPath(path,p);p.color=Color.rgb(5,20,35);c.drawCircle(e.x,e.y,e.r*.32f,p)}
            else->{p.style=Paint.Style.STROKE;p.strokeWidth=e.r*.22f;c.drawCircle(e.x,e.y,e.r,p);c.drawCircle(e.x,e.y,e.r*.62f,p);for(i in 0..5){val a=TAU*i/6+e.phase;c.drawLine(e.x+cos(a)*e.r*.65f,e.y+sin(a)*e.r*.65f,e.x+cos(a)*e.r*1.25f,e.y+sin(a)*e.r*1.25f,p)};p.style=Paint.Style.FILL;p.color=Color.WHITE;c.drawCircle(e.x,e.y,e.r*.2f,p)}
        }
        if(e.type>=3){p.color=Color.argb(150,0,0,0);c.drawRect(e.x-e.r,e.y-e.r*1.35f,e.x+e.r,e.y-e.r*1.18f,p);p.color=Color.rgb(110,255,160);c.drawRect(e.x-e.r,e.y-e.r*1.35f,e.x-e.r+2*e.r*(e.hp/e.maxHp),e.y-e.r*1.18f,p)}
    }

    private fun drawHud(c:Canvas){
        p.color=Color.argb(170,5,8,20);c.drawRoundRect(width*.03f,height*.025f,width*.97f,height*.13f,18f,18f,p)
        p.color=Color.rgb(45,55,80);c.drawRoundRect(width*.06f,height*.048f,width*.52f,height*.067f,10f,10f,p);p.color=Color.rgb(255,75,110);c.drawRoundRect(width*.06f,height*.048f,width*.06f+width*.46f*(hp/maxHp),height*.067f,10f,10f,p)
        text(c,"NV $level",height*.058f,width*.034f,Color.WHITE);text(c,"${time.toInt()}s",height*.103f,width*.045f,Color.rgb(88,230,255))
        val obj=when(objective){0->"ELIMINE A HORDA";1->"COLETE FRAGMENTOS";2->"SOBREVIVA";3->"DERROTE O NÚCLEO";else->"RESISTA À RUPTURA"}
        text(c,obj,height*.155f,width*.033f,Color.WHITE);text(c,"$objectiveProgress / $objectiveTarget",height*.188f,width*.030f,Color.rgb(110,255,160))
        if(combo>1)text(c,"COMBO x$combo",height*.24f,width*.043f,Color.rgb(255,190,70))
    }

    private fun drawUpgrade(c:Canvas){p.color=Color.argb(225,3,5,15);c.drawRect(0f,0f,width.toFloat(),height.toFloat(),p);text(c,"ESCOLHA UMA RUPTURA",height*.22f,width*.056f,Color.WHITE);val names=arrayOf("POTÊNCIA","CADÊNCIA","IMPULSO","DISPARO DUPLO","VITALIDADE","MAGNETISMO","PERFURAÇÃO","BLINDAGEM","NOVO ECO");for(i in 0..2){val l=i*width/3f+12f;val r=(i+1)*width/3f-12f;p.color=Color.rgb(18,28,56);c.drawRoundRect(l,height*.35f,r,height*.68f,24f,24f,p);p.color=if(i==1)Color.rgb(196,92,255) else Color.rgb(88,230,255);c.drawCircle((l+r)/2,height*.44f,width*.045f,p);textAt(c,names[choices[i]],(l+r)/2,height*.56f,width*.031f,Color.WHITE)}}
    private fun drawDead(c:Canvas){p.color=Color.argb(225,3,5,15);c.drawRect(0f,0f,width.toFloat(),height.toFloat(),p);text(c,"RUPTURA COLAPSADA",height*.38f,width*.060f,Color.WHITE);text(c,"${time.toInt()}s • $kills baixas",height*.49f,width*.045f,Color.rgb(88,230,255));text(c,"TOQUE PARA REENTRAR",height*.66f,width*.042f,Color.WHITE)}
    private fun drawVictory(c:Canvas){p.color=Color.argb(230,3,5,15);c.drawRect(0f,0f,width.toFloat(),height.toFloat(),p);text(c,"NÚCLEO DESTRUÍDO",height*.38f,width*.062f,Color.rgb(110,255,160));text(c,"MISSÃO CONCLUÍDA",height*.49f,width*.046f,Color.WHITE);text(c,"TOQUE PARA NOVA INCURSÃO",height*.66f,width*.040f,Color.WHITE)}
    private fun text(c:Canvas,s:String,y:Float,size:Float,color:Int){textAt(c,s,width/2f,y,size,color)}
    private fun textAt(c:Canvas,s:String,x:Float,y:Float,size:Float,color:Int){p.textAlign=Paint.Align.CENTER;p.textSize=size;p.color=color;c.drawText(s,x,y,p)}
    private fun Canvas.drawDiamond(x:Float,y:Float,r:Float,paint:Paint){val path=Path();path.moveTo(x,y-r);path.lineTo(x+r,y);path.lineTo(x,y+r);path.lineTo(x-r,y);path.close();drawPath(path,paint)}
}
