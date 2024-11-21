class SimpleKalmanFilter {
    constructor(r = 1, q = 1, a = 1, b = 0, h = 1) {
        this.r = r; // 测量噪声
        this.q = q; // 过程噪声
        this.a = a; // 状态转移系数
        this.b = b; // 控制输入系数
        this.h = h; // 测量系数
        this.x = 0; // 初始估计
        this.p = 1; // 初始误差协方差
    }

    update(measurement) {
        // 预测
        const predictedX = this.a * this.x;
        const predictedP = this.a * this.p * this.a + this.q;

        // 更新
        const k = predictedP * this.h / (this.h * predictedP * this.h + this.r);
        this.x = predictedX + k * (measurement - this.h * predictedX);
        this.p = (1 - k * this.h) * predictedP;

        return this.x;
    }
}
