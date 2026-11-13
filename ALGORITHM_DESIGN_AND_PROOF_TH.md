# BPCB-(1,2): Algorithm Design and Safety Proof

ชื่อเต็ม: **Combined One- and Two-Box Prefix Blocker-Closure Bound**  
ชื่อย่อที่ใช้ในโครงงาน: **BPCB-(1,2)**  
สถานะ: implemented candidate algorithm พร้อม exact differential validation

## 1. จาก BPCB-1 สู่ box prefix

BPCB-1 นับสกรูสีอื่นที่ถูกบังคับให้ถอดก่อน active box ใบปัจจุบันเต็ม
แต่บาง dead state เกิดจาก constraint ของกล่องถัดไป ซึ่ง BPCB-1 จะเห็นหลังจากขยาย state ไปแล้ว

BPCB-2 พิจารณา active box และกล่องถัดไปพร้อมกัน โดยนับเฉพาะสกรูสีที่ไม่มี
ในทั้งสองกล่อง เพราะสกรูเหล่านั้นไม่สามารถออกจาก tray ได้ตลอด prefix

BPCB-1 และ BPCB-2 ไม่ได้ dominate กัน:

- BPCB-1 อาจแรงกว่า เพราะสีของกล่องที่สองยังถือเป็น off-color ต่อกล่องแรก
- BPCB-2 อาจแรงกว่า เพราะเห็น blocker ที่จำเป็นสำหรับกล่องที่สองตั้งแต่ก่อนกล่องแรกเต็ม

อัลกอริทึม combined จึง prune เมื่อ bound ใด bound หนึ่งพิสูจน์ว่า capacity ไม่พอ

## 2. Prefix demand

ให้ prefix เริ่มจาก active box ยาว `k` ใบ

สำหรับสี `c` กำหนด:

```text
demand_k(c) = จำนวนช่องของสี c ที่ต้องเติมเพื่อจบ prefix
```

สำหรับ active box ใช้เฉพาะช่องที่ยังขาด ส่วนกล่องถัดไปใช้ capacity เต็ม

สกรูสี `c` ที่มีอยู่ใน tray สามารถเติม demand ภายใน prefix ได้ไม่เกิน `demand_k(c)`
ดังนั้นจำนวน target screws สี `c` ที่ต้องมาจากกระดานอย่างน้อยคือ:

```text
board_need_k(c) = max(0, demand_k(c) - tray_count(c))
```

## 3. Persistent tray occupancy

สกรูใน tray ที่ไม่สามารถถูก prefix รับได้ต้องค้างอยู่จน prefix จบ:

```text
persistent_tray_k =
    sum over colors c of max(0, tray_count(c) - demand_k(c))
```

ถ้าสีไม่ปรากฏใน prefix จะมี demand เท่ากับศูนย์และถูกนับทั้งหมด

## 4. Prefix blocker-closure lower bound

สำหรับแต่ละสีใน prefix เลือก target screws จากกระดานตามจำนวน `board_need_k(c)`
ให้ union ของ targets ทุกสีเป็น `U`

คำนวณ recursive blocker closure `C_X(U)` ตามนิยามเดียวกับ BPCB-1

นับเฉพาะ closure screws ที่สีไม่ปรากฏใน prefix:

```text
offprefix_cost_k(U) =
    number of distinct t in C_X(U)
    where color(t) is absent from the prefix
```

จากนั้นกำหนด:

```text
L_k(X) = minimum offprefix_cost_k(U)
         over every target selection satisfying board_need_k
```

## 5. Safe pruning rule

```text
if persistent_tray_k(X) + L_k(X) > W:
    prune X
```

หาก remaining screws สีใดมีน้อยกว่า `board_need_k(c)` สถานะก็ prune ได้ทันที

## 6. Safety proof สำหรับ prefix k

สมมติว่ามี solution continuation ที่ทำให้กล่องทั้ง `k` ใบใน prefix เต็ม

พิจารณาสกรูจากกระดานที่ solution ใช้เติม demand ของแต่ละสีหลังหักสกรูเริ่มต้นใน tray
target set จริงนี้เป็นหนึ่งในชุด `U` ที่นิยาม `L_k(X)`

ก่อน target ทุกตัวจะถูกถอด active blocking plates ต้องถูกทำให้ว่าง และสกรูที่บัง
blocking screws ต้องถูกนำออกแบบ recursive ดังนั้น closure ของ target set จริงต้องถูกถอด
ไม่ช้ากว่าจังหวะที่ prefix เสร็จ

closure screw ที่สีไม่ปรากฏใน prefix:

1. เข้ากล่องใดใน prefix ไม่ได้
2. ไม่มี action อื่นนำมันออกจาก tray
3. จึงยังค้างอยู่พร้อมกันเมื่อ prefix จบ

นอกจากนี้ initial tray ส่วนที่เกิน total prefix demand ก็ยังค้างอยู่ จำนวน tray occupancy
ใน continuation จริงจึงไม่น้อยกว่า:

```text
persistent_tray_k(X) + offprefix_cost_k(U_actual)
```

และเพราะ `L_k` เป็น minimum:

```text
offprefix_cost_k(U_actual) >= L_k(X)
```

หากผลรวม lower bound มากกว่า `W` continuation ดังกล่าวเป็นไปไม่ได้ เกิดข้อขัดแย้ง
ดังนั้น pruning rule ปลอดภัย

## 7. Safety ของ combined BPCB-(1,2)

ให้ predicates `P1(X)` และ `P2(X)` หมายถึง BPCB-1 และ BPCB-2 พิสูจน์ว่า state ตาย

ทั้งสอง predicate sound จาก theorem ข้างต้น ดังนั้น:

```text
P1(X) OR P2(X)
```

ก็ sound เช่นกัน Combined implementation ตรวจ BPCB-1 ก่อน หากยังไม่ prune จึงตรวจ BPCB-2

## 8. Combination limit

จำนวน target selections อาจโตเร็วเมื่อ prefix ยาวหรือมีสีจำนวนมาก

Implementation ตั้ง `max_combinations=50,000` สำหรับ BPCB-2 หากเกิน limit:

- ไม่ใช้ heuristic estimate ที่อาจสูงเกินจริง
- คืน lower bound ที่อ่อนลงเหลือเฉพาะ `persistent_tray_k`
- จึงเสียโอกาส prune แต่ไม่เสีย correctness

## 9. Implementation optimizations

- immutable lookup maps ถูก cache ต่อ level
- screw sets, plate contents, colors และ closures ใช้ integer bitsets
- recursive closure คำนวณหนึ่งครั้งต่อ candidate ต่อ state
- closure ของ target set รวมด้วย bitwise OR
- cardinality ใช้ `bit_count()`
- target combinations ใช้ exact enumeration ภายใต้ combination limit

## 10. Validation evidence

- Unit tests 27 tests ผ่าน
- Toy T9: BPCB-1 ไม่ prune ที่ root แต่ BPCB-2 พิสูจน์ forced overflow ได้ทันที
- Tight T9 ที่เพิ่ม capacity หนึ่งช่องไม่ถูก prune และพบ solution
- Exact status ตรง baseline ทั้ง 20 multibase dataset instances
- Differential mutations: checked 99, skipped 1 เพราะ limit, mismatches 0
- Combined solver solutions ผ่าน replay validator

## 11. Scope ของ novelty claim

สิ่งที่อาจเสนอเป็น contribution ไม่ใช่ DFS, memoization, bitset หรือ dependency closure แยกกัน
แต่คือ:

> การสร้าง admissible forced-storage lower bound จาก recursive blocker closure และ ordered
> color-box prefix แล้วใช้หลาย prefix lengths ร่วมกันเพื่อตัด state ของปริศนาถอดสกรู

ยังต้องทำ prior-art search เฉพาะ formulation นี้ก่อนใช้คำว่า first/new อย่างเด็ดขาด

