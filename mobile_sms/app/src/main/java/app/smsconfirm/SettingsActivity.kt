package app.smsconfirm

import android.os.Bundle
import android.util.Base64
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import app.smsconfirm.data.Prefs
import app.smsconfirm.databinding.ActivitySettingsBinding
import app.smsconfirm.repo.SmsRepository
import kotlinx.coroutines.launch
import org.json.JSONObject

class SettingsActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySettingsBinding
    private lateinit var prefs: Prefs
    private lateinit var repo: SmsRepository

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)

        prefs = Prefs(this)
        repo = SmsRepository.get(this)

        binding.inputServerUrl.setText(prefs.serverUrl)
        binding.inputApiToken.setText(prefs.apiToken)

        binding.btnApplySetupCode.setOnClickListener { applySetupCode() }
        binding.btnSave.setOnClickListener { save() }
        binding.btnTestConnection.setOnClickListener { save(thenTest = true) }
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }

    /**
     * «کد راه‌اندازی» from the panel: "SMS1:" + base64url(JSON {"u": server address, "t": device token}), no padding
     * (backend apps/payments_sms/device_url.py::setup_code). Fills the two fields below, saves and tests the connection.
     */
    private fun applySetupCode() {
        val parsed = parseSetupCode(binding.inputSetupCode.text?.toString().orEmpty())
        if (parsed == null) {
            binding.resultText.text = getString(R.string.setup_code_bad)
            return
        }
        binding.inputServerUrl.setText(parsed.first)
        binding.inputApiToken.setText(parsed.second)
        save(thenTest = true)
    }

    private fun save(thenTest: Boolean = false) {
        val url = binding.inputServerUrl.text?.toString()?.trim().orEmpty()
        val token = binding.inputApiToken.text?.toString()?.trim().orEmpty()

        if (url.isBlank() || token.isBlank()) {
            binding.resultText.text = getString(R.string.settings_fill_both)
            return
        }
        prefs.serverUrl = url
        prefs.apiToken = token

        if (!thenTest) {
            finish()
            return
        }

        binding.btnTestConnection.isEnabled = false
        binding.resultText.text = getString(R.string.settings_testing)
        lifecycleScope.launch {
            val result = repo.ping()
            binding.btnTestConnection.isEnabled = true
            binding.resultText.text = if (result.isSuccess) {
                getString(R.string.settings_test_ok, result.getOrNull()?.device ?: "")
            } else {
                getString(R.string.settings_test_fail, result.exceptionOrNull()?.message ?: "")
            }
        }
    }

    companion object {
        private const val SETUP_PREFIX = "SMS1:"

        /** (server address, token) or null when the text is not a valid setup code. */
        fun parseSetupCode(raw: String): Pair<String, String>? {
            val code = raw.trim()
            if (!code.startsWith(SETUP_PREFIX)) return null
            return try {
                val bytes = Base64.decode(code.removePrefix(SETUP_PREFIX), Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
                val json = JSONObject(String(bytes, Charsets.UTF_8))
                val url = json.optString("u").trim()
                val token = json.optString("t").trim()
                if (url.startsWith("http") && token.isNotEmpty()) url to token else null
            } catch (e: Exception) {
                null
            }
        }
    }
}
