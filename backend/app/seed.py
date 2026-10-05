"""初始化演示数据：账号、实验室、设备、知识库、预约记录。

首次启动时自动写入；已存在数据则跳过，不会覆盖。
"""
from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import func, select

from app.core.security import hash_password
from app.database import SessionLocal
from app.models import Equipment, Lab, LabDocument, Reservation, User

logger = logging.getLogger("lab-booking.seed")


# --------------------------------------------------------------------- 知识库
GENERAL_DOCS: list[dict] = [
    {
        "title": "实验室预约管理办法（总则）",
        "category": "规章制度",
        "content": (
            "为规范实验室资源使用，所有实验室实行线上预约制。学生须至少提前 2 小时提交预约申请，"
            "经管理员审核通过后方可使用。单次预约时长不少于 30 分钟、不超过 8 小时，且不得超过实验室开放时间。"
            "每人每天在同一实验室最多预约 2 个时段，全平台每天最多 4 个时段。"
            "预约成功后请按时到达，凭学号在实验室门口签到。"
            "如需取消预约，请在开始时间前 2 小时于「我的预约」中操作，以免影响个人信用分。"
            "连续 3 次预约未到且未取消，将暂停预约权限 30 天。"
            "实验室内禁止吸烟、饮食、喧哗；离开前须关闭设备电源、整理台面、关好门窗。"
        ),
    },
    {
        "title": "实验室安全须知",
        "category": "安全规范",
        "content": (
            "进入实验室必须穿实验服，长发须束起，禁止穿拖鞋、凉鞋进入化学与生物类实验室。"
            "使用电器设备前应检查线路是否破损，发现漏电、异味、冒烟立即切断电源并报告管理员。"
            "化学试剂须按标签取用，严禁混装、品尝、直接闻嗅；涉及挥发性试剂的操作必须在通风橱内进行。"
            "实验废弃物按类别投放至指定回收容器，严禁倒入下水道。"
            "实验室内须熟知灭火器、洗眼器、急救箱位置；发生火情先断电、再用灭火器扑救，同时拨打校内应急电话。"
            "严禁私自改装电路、拆卸设备、超负荷用电，严禁携带无关人员进入实验室。"
        ),
    },
    {
        "title": "设备使用与损坏赔偿规定",
        "category": "规章制度",
        "content": (
            "大型精密仪器须经培训并考核合格后方可独立操作，未培训人员须在管理员指导下使用。"
            "使用前应填写设备使用记录，核对设备状态；使用后按规程关机、复位、清洁并归还配件。"
            "设备出现故障应立即停止使用、挂上「故障待修」标识并报修，严禁自行拆装。"
            "因违规操作造成设备损坏的，按维修费用的 30%—100% 承担赔偿；属正常损耗的免于赔偿。"
            "设备外借须经实验室主任审批，填写外借单并按时归还，逾期未还将暂停其借用资格。"
        ),
    },
    {
        "title": "实验室开放时间与考勤要求",
        "category": "使用指南",
        "content": (
            "全校实验室常规开放时间为工作日 08:00—22:00，周末及节假日 09:00—17:00。"
            "具体以每间实验室详情页标注的开放时间为准，部分科研实验室实行 24 小时刷卡开放。"
            "预约时段开始 15 分钟后仍未签到的，系统自动记为一次违约，该时段释放给其他同学。"
            "连续使用超过预约结束时间 30 分钟视为超时占用，将记录违约并警告。"
            "实验楼实行门禁管理，非开放时段进入需提前向管理员申请临时权限。"
        ),
    },
    {
        "title": "AI 实验室使用规范",
        "category": "使用指南",
        "content": (
            "AI 实验室配备 GPU 计算服务器，主要用于深度学习模型训练、数据标注与算法验证。"
            "GPU 资源紧张，单次训练任务默认限时 4 小时，超长任务请提交任务计划书申请排队。"
            "禁止在服务器上运行与科研无关的挖矿、爬虫、对外攻击等程序，禁止存储违法违规数据。"
            "数据集与模型权重请存放于个人目录，公共目录仅用于共享只读数据。"
            "训练结束后请释放显存、清理临时文件，未释放资源超过 1 小时将强制回收。"
        ),
    },
    {
        "title": "预约审核与优先级规则",
        "category": "使用指南",
        "content": (
            "预约提交后由实验室管理员在 24 小时内完成审核，审核结果会通过站内消息与「我的预约」展示。"
            "同一时段存在多条申请时，按以下优先级审核：课程教学任务 > 毕业设计/科研项目 > 学生自主练习。"
            "审核通过后若因故不能使用，请及时取消，以便他人预约。被驳回的预约会注明驳回原因。"
            "面向全校开设的实验课程可申请整学期固定时段，由教务处统一提交，不占用个人预约额度。"
        ),
    },
    {
        "title": "违规行为处理办法",
        "category": "规章制度",
        "content": (
            "下列行为记违规：预约后未到且未取消；将账号借予他人使用；在实验室内饮食、吸烟；"
            "私自搬动或改装设备；不按规定处理实验废弃物；超时占用且不听劝阻。"
            "首次违规给予口头警告并记录；第二次违规暂停预约权限 14 天；第三次违规暂停 30 天并通报学院；"
            "造成设备损坏或安全事故的，除赔偿外还将按学校学生管理规定处理。"
            "个人信用分初始为 100 分，每次违规扣 10 分，低于 60 分将限制预约权限。"
        ),
    },
]


# --------------------------------------------------------------------- 实验室
LABS: list[dict] = [
    {
        "name": "人工智能实验室",
        "code": "LAB-AI-301",
        "building": "信息楼",
        "room": "301",
        "capacity": 40,
        "open_time": "08:00",
        "close_time": "22:00",
        "tags": "AI,深度学习,GPU",
        "description": "面向人工智能与数据科学方向，配备 GPU 计算服务器与预装深度学习框架的工作站。",
        "equipments": [
            ("GPU 计算服务器", "NVIDIA A100 80G × 4", 2, "normal"),
            ("深度学习工作站", "RTX 4090 / i9-13900K", 20, "normal"),
            ("高性能交换机", "H3C S6520", 2, "normal"),
            ("86 寸智慧屏", "希沃 MC86", 1, "normal"),
        ],
    },
    {
        "name": "嵌入式系统实验室",
        "code": "LAB-EMB-205",
        "building": "信息楼",
        "room": "205",
        "capacity": 32,
        "open_time": "08:00",
        "close_time": "21:00",
        "tags": "嵌入式,单片机,物联网",
        "description": "面向嵌入式开发与物联网方向，提供单片机开发板、示波器与焊接工位。",
        "equipments": [
            ("嵌入式开发套件", "STM32F407 探索者", 30, "normal"),
            ("数字示波器", "泰克 TBS1102B", 12, "normal"),
            ("直流稳压电源", "固纬 GPS-3303C", 12, "repair"),
            ("恒温焊台", "白光 FX-888D", 10, "normal"),
        ],
    },
    {
        "name": "计算机网络实验室",
        "code": "LAB-NET-402",
        "building": "信息楼",
        "room": "402",
        "capacity": 36,
        "open_time": "08:00",
        "close_time": "22:00",
        "tags": "网络,路由交换,安全",
        "description": "配备企业级路由交换设备与网络仿真平台，支持网络工程与信息安全实训。",
        "equipments": [
            ("企业级路由器", "华为 AR2220", 10, "normal"),
            ("三层交换机", "华为 S5700", 10, "normal"),
            ("机架式服务器", "戴尔 R740", 6, "normal"),
            ("网络测试仪", "FLUKE LinkRunner", 4, "normal"),
        ],
    },
    {
        "name": "化学分析实验室",
        "code": "LAB-CHE-108",
        "building": "实训楼",
        "room": "108",
        "capacity": 28,
        "open_time": "08:30",
        "close_time": "17:30",
        "tags": "化学,分析,试剂",
        "description": "配备通风橱与精密分析仪器，用于化学定量分析与样品前处理实验。",
        "equipments": [
            ("高效液相色谱仪", "安捷伦 1260", 2, "normal"),
            ("电子分析天平", "梅特勒 ME204", 8, "normal"),
            ("通风橱", "ESCO 1.5m", 6, "normal"),
            ("酸度计", "雷磁 PHS-3C", 16, "normal"),
        ],
    },
    {
        "name": "生物医学实验室",
        "code": "LAB-BIO-210",
        "building": "实训楼",
        "room": "210",
        "capacity": 24,
        "open_time": "08:30",
        "close_time": "18:00",
        "tags": "生物,医学,显微",
        "description": "面向生物医学工程，配备生物安全柜、培养箱与荧光显微成像系统。",
        "equipments": [
            ("荧光显微镜", "奥林巴斯 BX53", 4, "normal"),
            ("生物安全柜", "力康 HFsafe-1200", 3, "normal"),
            ("恒温培养箱", "上海一恒 BPX-82", 6, "normal"),
            ("高速离心机", "艾本德 5424R", 4, "normal"),
        ],
    },
    {
        "name": "电子电工实验室",
        "code": "LAB-EE-102",
        "building": "实训楼",
        "room": "102",
        "capacity": 48,
        "open_time": "08:00",
        "close_time": "20:00",
        "tags": "电工,电子,基础",
        "description": "基础电类实验教学场地，提供电工实验台与模拟电子实验箱。",
        "equipments": [
            ("电工实验台", "浙江天煌 THETDG-1", 24, "normal"),
            ("模拟电子实验箱", "THM-1", 24, "normal"),
            ("数字万用表", "福禄克 17B+", 30, "normal"),
            ("函数信号发生器", "普源 DG1022Z", 20, "normal"),
        ],
    },
    {
        "name": "智能制造实训中心",
        "code": "LAB-IM-001",
        "building": "工程训练中心",
        "room": "101",
        "capacity": 30,
        "open_time": "08:00",
        "close_time": "18:00",
        "tags": "智能制造,机器人,数控",
        "description": "集成工业机器人与数控加工单元，支撑智能制造方向综合实训。",
        "equipments": [
            ("六轴工业机器人", "ABB IRB 1200", 4, "normal"),
            ("桌面级数控机床", "泰克数控 TK-320", 6, "normal"),
            ("3D 打印机", "拓竹 X1-Carbon", 8, "repair"),
            ("激光雕刻机", "雷宇 6040", 2, "normal"),
        ],
    },
    {
        "name": "虚拟现实实验室",
        "code": "LAB-VR-305",
        "building": "信息楼",
        "room": "305",
        "capacity": 20,
        "open_time": "09:00",
        "close_time": "21:00",
        "tags": "VR,虚拟现实,交互",
        "description": "面向数字媒体与虚拟仿真，配备 VR 头显、动作捕捉与图形工作站。",
        "equipments": [
            ("VR 头显", "Meta Quest 3", 12, "normal"),
            ("动作捕捉系统", "OptiTrack Prime 13", 1, "normal"),
            ("图形工作站", "RTX 4080", 10, "normal"),
            ("全景相机", "Insta360 Pro 2", 2, "normal"),
        ],
        "status": "maintenance",
    },
]

LAB_DOCS: dict[str, list[dict]] = {
    "人工智能实验室": [
        {
            "title": "AI 实验室 GPU 服务器使用说明",
            "category": "设备操作",
            "content": (
                "GPU 服务器通过 SSH 登录，账号与实验室管理系统一致。"
                "登录后先执行 nvidia-smi 查看显存占用，空闲后方可提交训练任务。"
                "训练任务建议使用 screen 或 tmux 保持后台运行，避免 SSH 断开导致任务中断。"
                "单卡显存占用超过 90% 时请勿再提交新任务。任务结束须执行释放脚本 gpu-release。"
                "禁止在服务器上安装来源不明的软件包、禁止开放公网端口。"
            ),
        }
    ],
    "化学分析实验室": [
        {
            "title": "化学实验室个人防护与应急处理",
            "category": "安全规范",
            "content": (
                "进入化学分析实验室必须佩戴护目镜与实验手套。"
                "少量酸液溅到皮肤立即用大量清水冲洗 15 分钟并涂抹碳酸氢钠溶液；"
                "碱液溅到皮肤冲洗后涂抹硼酸溶液。试剂溅入眼睛立即使用洗眼器冲洗并就医。"
                "有机溶剂着火严禁用水扑救，应使用干粉或二氧化碳灭火器。"
                "所有废液须倒入贴有标签的废液桶，按有机废液、无机废液、含重金属废液分类收集。"
            ),
        }
    ],
    "智能制造实训中心": [
        {
            "title": "工业机器人与数控设备安全操作",
            "category": "设备操作",
            "content": (
                "机器人运行时人员必须站在安全围栏之外，严禁进入运动范围。"
                "示教编程前须将控制柜切换至手动模式并按下急停。"
                "数控机床启动前确认工件夹紧、刀具装正；加工中不得打开防护门。"
                "操作旋转设备禁止佩戴手套与围巾，长发须完全束入工作帽。"
                "实训结束后须清理铁屑、复位坐标、关闭气源与总电源。"
            ),
        }
    ],
    "虚拟现实实验室": [
        {
            "title": "VR 设备使用与卫生要求",
            "category": "设备操作",
            "content": (
                "VR 头显使用前请使用酒精棉片擦拭镜片与面罩。"
                "体验时请在划定区域内活动，注意线缆，避免绊倒。"
                "单次连续佩戴建议不超过 30 分钟，出现眩晕立即停止并到通风处休息。"
                "动作捕捉场地内不得携带金属物品，需按要求穿着动捕服与标记点。"
            ),
        }
    ],
}


def _seed_users(db) -> None:
    if db.scalar(select(func.count(User.id))):
        return
    users = [
        User(username="admin", password=hash_password("admin123"), name="系统管理员",
             role="admin", email="admin@lab.edu.cn", phone="13800000000", college="实验室管理中心"),
        User(username="teacher", password=hash_password("teacher123"), name="李老师",
             role="admin", email="li@lab.edu.cn", phone="13800000001", college="计算机学院"),
        User(username="student", password=hash_password("student123"), name="张同学",
             role="student", email="zhang@stu.edu.cn", phone="13900000001",
             student_no="2023010101", college="计算机学院"),
        User(username="wangfang", password=hash_password("123456"), name="王芳",
             role="student", email="wangf@stu.edu.cn", student_no="2023010102", college="电子信息学院"),
        User(username="liulei", password=hash_password("123456"), name="刘磊",
             role="student", email="liul@stu.edu.cn", student_no="2023010103", college="机械工程学院"),
        User(username="chenjing", password=hash_password("123456"), name="陈静",
             role="student", email="chenj@stu.edu.cn", student_no="2023010104", college="化学化工学院"),
    ]
    db.add_all(users)
    db.commit()
    logger.info("已写入 %s 个演示账号", len(users))


def _seed_labs(db) -> None:
    if db.scalar(select(func.count(Lab.id))):
        return
    for item in LABS:
        equipments = item.pop("equipments", [])
        lab = Lab(**item)
        db.add(lab)
        db.flush()
        for name, model, qty, status in equipments:
            db.add(Equipment(lab_id=lab.id, name=name, model=model, quantity=qty,
                             status=status, description=f"{name}，归属于{lab.name}"))
    db.commit()
    logger.info("已写入 %s 间实验室及配套设备", len(LABS))


def _seed_documents(db) -> None:
    if db.scalar(select(func.count(LabDocument.id))):
        return
    from app.ai import rag

    docs: list[LabDocument] = [LabDocument(**d) for d in GENERAL_DOCS]
    for lab_name, items in LAB_DOCS.items():
        lab = db.scalar(select(Lab).where(Lab.name == lab_name))
        if not lab:
            continue
        for item in items:
            docs.append(LabDocument(lab_id=lab.id, **item))
    db.add_all(docs)
    db.commit()
    for doc in docs:
        rag.index_document(db, doc)
    logger.info("已写入 %s 篇知识库文档并建立向量索引", len(docs))


def _seed_reservations(db) -> None:
    if db.scalar(select(func.count(Reservation.id))):
        return
    students = db.scalars(select(User).where(User.role == "student")).all()
    labs = db.scalars(select(Lab).order_by(Lab.id)).all()
    if not students or not labs:
        return
    today = dt.date.today()
    plan = [
        # (学生索引, 实验室索引, 天偏移, 开始, 结束, 用途, 人数, 状态)
        (0, 0, 0, "09:00", "11:00", "深度学习课程实验：图像分类模型训练", 6, "approved"),
        (1, 1, 0, "14:00", "16:00", "嵌入式课程设计：STM32 串口通信调试", 4, "approved"),
        (2, 2, 1, "10:00", "12:00", "网络工程实训：VLAN 配置实验", 5, "pending"),
        (3, 3, 1, "14:30", "16:30", "分析化学实验：样品前处理", 8, "pending"),
        (0, 4, 2, "09:30", "11:30", "生物医学创新项目：细胞成像观察", 3, "pending"),
        (1, 6, 3, "13:00", "17:00", "智能制造综合实训：机器人轨迹编程", 10, "approved"),
        (2, 5, -3, "08:00", "10:00", "电工电子实验：放大器电路测试", 12, "finished"),
        (3, 0, -5, "15:00", "17:00", "毕业设计：模型调参与性能测试", 2, "finished"),
        (0, 2, -1, "19:00", "21:00", "学科竞赛备赛：网络攻防演练", 4, "rejected"),
        (1, 1, 4, "08:00", "10:00", "嵌入式竞赛培训", 8, "pending"),
        (2, 0, 5, "13:00", "15:00", "数据挖掘课程实验", 15, "pending"),
        (3, 3, -2, "09:00", "11:00", "化学分析补做实验", 6, "cancelled"),
    ]
    rows = []
    for si, li, offset, start, end, purpose, people, status in plan:
        student = students[si % len(students)]
        lab = labs[li % len(labs)]
        day = today + dt.timedelta(days=offset)
        row = Reservation(
            user_id=student.id,
            lab_id=lab.id,
            booking_date=day,
            start_time=start,
            end_time=end,
            purpose=purpose,
            people_count=min(people, lab.capacity),
            status=status,
        )
        if status in ("approved", "rejected"):
            row.reviewer_id = 1
            row.reviewed_at = dt.datetime.now() - dt.timedelta(days=1)
            row.review_remark = "审核通过，请按时到场" if status == "approved" else "该时段已有教学任务占用"
        rows.append(row)
    db.add_all(rows)
    db.commit()
    logger.info("已写入 %s 条演示预约记录", len(rows))


def ensure_seed() -> None:
    db = SessionLocal()
    try:
        _seed_users(db)
        _seed_labs(db)
        _seed_documents(db)
        _seed_reservations(db)
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("初始化演示数据失败")
        raise
    finally:
        db.close()
