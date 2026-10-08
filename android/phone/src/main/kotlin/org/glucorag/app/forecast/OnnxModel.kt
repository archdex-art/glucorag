package org.glucorag.app.forecast

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.nio.FloatBuffer

/**
 * The exported network run by ONNX Runtime. [bytes] is `model.onnx`; input and output names come
 * from [meta]. Sessions are thread-safe, so one instance serves the whole app.
 */
class OnnxModel(bytes: ByteArray, private val meta: DeviceMeta) : QuantileModel, AutoCloseable {
    private val env = OrtEnvironment.getEnvironment()
    // One forecast every ~5 minutes on a tiny graph: a single thread is plenty and spares the battery.
    // KleidiAI kernels pick SME/i8mm paths from CPU feature flags, and some CPUs (including the
    // Android emulator on Apple silicon) report features they then fault on (SIGILL). The graph
    // is tiny, so the portable MLAS kernels cost nothing noticeable.
    private val options = OrtSession.SessionOptions().apply {
        setIntraOpNumThreads(1)
        addConfigEntry("mlas.disable_kleidiai", "1")
    }
    private val session: OrtSession = env.createSession(bytes, options)

    override fun run(static: FloatArray, xEnc: Array<FloatArray>, xDec: FloatArray): Array<FloatArray> {
        val (staticName, encName, decName) = meta.inputs
        val enc = FloatArray(xEnc.size * 2) { xEnc[it / 2][it % 2] }
        tensor(static, 1, static.size.toLong()).use { s ->
            tensor(enc, 1, xEnc.size.toLong(), 2).use { e ->
                tensor(xDec, 1, xDec.size.toLong(), 1).use { d ->
                    session.run(mapOf(staticName to s, encName to e, decName to d), setOf(meta.output)).use { result ->
                        @Suppress("UNCHECKED_CAST")
                        return (result.get(0).value as Array<Array<FloatArray>>)[0]
                    }
                }
            }
        }
    }

    private fun tensor(data: FloatArray, vararg shape: Long): OnnxTensor =
        OnnxTensor.createTensor(env, FloatBuffer.wrap(data), shape)

    override fun close() {
        session.close()
        options.close()
    }
}
