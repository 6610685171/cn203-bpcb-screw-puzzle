# ผลการทดลองสุดท้าย: BPCB-(1,2)

ผลนี้มาจาก frozen benchmark 100 instances ซึ่งสร้างและติด exact label ด้วย
Memoized DFS ก่อนเปิดผล BPCB โดยแบ่งเป็น development 60 และ final hold-out 40
instances ข้อมูลและ code หลักถูกตรึงด้วย SHA-256 ใน
`generated_final_dataset/manifest.json` และ `freeze.json`

## ผลรวม

| Split | Method | Instances | Nodes | ลด nodes จาก baseline | ผลรวม median time | Speedup |
|---|---:|---:|---:|---:|---:|---:|
| Development | Memoized DFS | 60 | 59,018 | 0.00% | 22,594.28 ms | 1.000x |
| Development | BPCB-1 | 60 | 45,691 | 22.58% | 20,632.54 ms | 1.095x |
| Development | BPCB-2 | 60 | 22,462 | 61.94% | 10,836.51 ms | 2.085x |
| Development | BPCB-(1,2) | 60 | 20,114 | 65.92% | 10,997.65 ms | 2.054x |
| Final hold-out | Memoized DFS | 40 | 44,549 | 0.00% | 17,768.65 ms | 1.000x |
| Final hold-out | BPCB-1 | 40 | 27,812 | 37.57% | 13,449.76 ms | 1.321x |
| Final hold-out | BPCB-2 | 40 | 21,684 | 51.33% | 11,629.61 ms | 1.528x |
| Final hold-out | BPCB-(1,2) | 40 | 15,972 | **64.15%** | 9,580.23 ms | **1.855x** |

ผล 400 instance-method combinations ตรงกับ frozen exact label ทั้งหมด และทุก
solution ที่คืนมาผ่าน replay validation ไม่พบ false prune ในชุดทดลองนี้

## ผล BPCB-(1,2) แยกตาม hold-out stratum

| Stratum | Instances | ลด nodes | Speedup | ความหมาย |
|---|---:|---:|---:|---|
| Raw direct | 10 | 2.32% | 0.560x | แทบไม่มี subtree ให้ตัด จึงเสีย bound overhead |
| General mutation | 10 | 44.21% | 1.292x | ได้ประโยชน์นอก crafted boundary cases |
| Capacity boundary | 20 | 72.33% | 2.271x | ตรงกับ forced-storage waste ที่ออกแบบ bound มาแก้ |

## Failure cases ที่เก็บไว้

`hol_level_11_raw` ขยาย 38 nodes เท่ากันทั้ง baseline และวิธีรวม แต่ median time
เพิ่มจาก 5.669 ms เป็น 15.662 ms หรือช้าประมาณ 2.76 เท่า เพราะ bound ไม่สามารถตัด
state ได้เลย

`hol_level_14_seed_141_boundary_01_unsolvable_W1` ลด nodes จาก 189 เป็น 162
(14.29%) แต่เวลาเพิ่มจาก 46.490 เป็น 55.426 ms แสดงว่า node reduction เล็กน้อยยัง
ไม่พอชดเชย overhead

## ข้อสรุป

ผล final hold-out สนับสนุนว่า BPCB-(1,2) ลด search waste ตาม primary metric ได้จริง
โดยไม่ทำให้คำตอบเปลี่ยน ภายใต้ static-geometry OSRP model วิธีนี้เหมาะกับ branch ที่
มี forced off-prefix screws และข้อจำกัด tray สูง แต่ไม่เหมาะกับ direct path ที่ baseline
เดินถึงคำตอบได้อยู่แล้ว

ข้อจำกัดคือ benchmark มาจาก generator เดียว, model ไม่รวม rigid-body rotation และ
ยังไม่ได้วัด peak memory โดยตรง การพัฒนาถัดไปที่สมเหตุสมผลคือเพิ่ม trigger ราคาถูก
เพื่อข้าม bound ใน state ที่มีลักษณะ direct path

## ไฟล์หลักฐาน

- `results/final/raw_results.csv`: ผลราย instance และเวลาทั้ง 5 รอบ
- `results/final/aggregate_summary.csv`: ผลรวมแยก split/stratum/method
- `results/final/environment.json`: environment, parameter และ algorithm hashes
- `results/final/nodes_scatter.png`: กราฟ baseline เทียบ BPCB-(1,2)
- `results/final/node_reduction.png`: กราฟ aggregate node reduction
- `EVALUATION_PROTOCOL_TH.md`: prediction และเกณฑ์ตัดสินที่บันทึกก่อนรัน

คำสั่งสร้างผลและกราฟใหม่จาก frozen manifest:

```bash
python3 scripts/run_final_evaluation.py --repeats 5 --warmup 1
```
