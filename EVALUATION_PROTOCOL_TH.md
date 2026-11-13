# แผนการทดลองสุดท้ายที่ตรึงไว้ก่อนเปิด Hold-out

เอกสารนี้บันทึกแผนการทดลองก่อนนำ BPCB ไปวัดกับชุด hold-out เพื่อป้องกันการเลือก
ข้อมูลหรือเปลี่ยน Algorithm หลังเห็นผลลัพธ์

## 1. คำถามการทดลอง

เมื่อใช้โจทย์เดียวกันและคำตอบต้องถูกต้องเท่ากัน BPCB ช่วยลดจำนวน state ที่
Memoized DFS ต้องขยายได้หรือไม่ และ overhead ของการคำนวณ bound ทำให้เวลาจริง
ดีขึ้นหรือแย่ลงเพียงใด

## 2. Algorithm ที่เปรียบเทียบ

- Baseline: Memoized DFS ซึ่ง cache เฉพาะ state ที่พิสูจน์แล้วว่าแก้ไม่ได้
- BPCB-1: Baseline + bound ของกล่องปัจจุบันหนึ่งกล่อง
- BPCB-2: Baseline + bound ของ prefix สองกล่อง
- BPCB-(1,2): ตรวจ BPCB-1 ก่อน และตรวจ BPCB-2 เฉพาะเมื่อ BPCB-1 ยังตัดไม่ได้

ทุกวิธีเป็น exact algorithm และใช้ลำดับการเลือก move เดียวกัน ต่างกันเฉพาะการตัด
subtree ที่ bound พิสูจน์แล้วว่าแก้ไม่ได้

## 3. ข้อมูลและการแยกชุด

ข้อมูลทั้งหมดมาจาก runtime export ของ Flutter ScrewJam generator ที่ source commit
`5ee0b84970eba12d4fd7f937bae162bf75ba61f3` แล้วแปลงเป็น discrete model เดียวกัน

- Development 60 instances: runtime base ระดับ 1–9 และระดับ 6 seed 61
- Hold-out 40 instances: runtime base ระดับ 11, 13, 14, 16, 19 และ seeded
  variants 111, 131, 141, 161, 191
- รวม 100 instances

ในแต่ละ split มีทั้ง raw level, general mutation และ capacity-boundary pair ที่มี
โจทย์ solvable/unsolvable อยู่คนละด้านของค่าความจุขั้นต่ำ

การคัดเลือกและติด label ใช้ Memoized DFS เท่านั้น ไม่ใช้ผลจาก BPCB โดยไฟล์
`generated_final_dataset/freeze.json` และ `manifest.json` เก็บ SHA-256 ของ code,
config, source fixture และทุก instance

## 4. ตัวแปรที่วัด

ตัวชี้วัดหลักคือ `nodes_expanded` เพราะตรงกับ waste ที่ต้องการลดและไม่ขึ้นกับ
ความผันผวนของเครื่อง ตัวชี้วัดประกอบคือเวลามัธยฐานจาก 5 รอบหลัง warm-up 1 รอบ,
จำนวน transition, bound checks, bound prunes, จำนวน combination ที่ bound ตรวจ และ
จำนวนครั้งที่ BPCB-2 fallback เพราะเกิน combination limit

Correctness ตรวจจาก status เทียบ exact label และ replay solution ทุกครั้งที่ solver
ตอบว่า solved

## 5. Prediction ที่บันทึกก่อนทดลอง

1. BPCB-(1,2) ควรลด node ได้ชัดที่สุดในกลุ่ม capacity-boundary โดยเฉพาะโจทย์
   unsolvable เพราะมี forced screws ที่ทำให้ tray overflow ก่อน search ไปถึง dead end
2. Raw level ที่หา solution ได้ตรง ๆ อาจแทบไม่ลด node เพราะ DFS ไม่ได้เดินเข้า
   dead subtree มากนัก
3. BPCB-2 อาจลด node มากกว่า BPCB-1 แต่เวลาจริงอาจแย่กว่าเมื่อจำนวน combination สูง
4. วิธีรวมควรได้ผลด้าน node ไม่น้อยกว่า BPCB-1 แต่ไม่จำเป็นต้องเร็วกว่า baseline

## 6. เกณฑ์ยอมรับว่าแนวคิดไม่เวิร์ก

จะถือว่าหลักฐานไม่สนับสนุนแนวคิด หากบน hold-out วิธีรวมไม่ลดจำนวน node รวมจาก
baseline หรือให้คำตอบผิดแม้แต่ instance เดียว ส่วนกรณีลด node ได้แต่เวลาช้าลงจะไม่
ถือว่า correctness ล้มเหลว แต่ต้องสรุปตรง ๆ ว่า bound ลด search waste แลกกับ
computational overhead และระบุขอบเขตที่เหมาะสม

## 7. ข้อจำกัดการรัน

- `max_nodes = 500,000` ต่อการรัน
- `time_limit = 5` วินาทีต่อการรัน
- `max_bound_combinations = 50,000`
- warm-up 1 รอบ และจับเวลา 5 รอบ
- Environment และ hash ที่ใช้จริงต้องถูกบันทึกพร้อมผลลัพธ์

