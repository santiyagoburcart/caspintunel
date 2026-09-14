package com.caspintunel.smsbridge

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.caspintunel.smsbridge.data.Prefs
import com.caspintunel.smsbridge.databinding.ActivitySettingsBinding
import com.caspintunel.smsbridge.repo.SmsRepository
import kotlinx.coroutines.launch

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

        binding.btnSave.setOnClickListener { save() }
        binding.btnTestConnection.setOnClickListener { save(thenTest = true) }
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
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
}
