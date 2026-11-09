package com.caspintunel.smsbridge

import android.os.Bundle
import android.view.View
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.caspintunel.smsbridge.data.Prefs
import com.caspintunel.smsbridge.databinding.ActivitySetupBinding
import com.caspintunel.smsbridge.repo.SmsRepository
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * First-run setup (v1.2.0), opened by MainActivity while no server / token is saved:
 *  1. "Scan QR code" — the built-in scanner (zxing-android-embedded, no other app needed) reads the panel's
 *     setup QR (SetupQr.parse); the connection is tested at once.
 *  2. "Enter manually" — server address + device token, like Settings.
 * On a successful test it returns to MainActivity. Back on the first screen leaves the app (MainActivity would only
 * send the user here again).
 */
class SetupActivity : AppCompatActivity() {

    private lateinit var binding: ActivitySetupBinding
    private lateinit var prefs: Prefs
    private lateinit var repo: SmsRepository

    private val scanner = registerForActivityResult(ScanContract()) { result ->
        result.contents?.let { onScanned(it) }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySetupBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = Prefs(this)
        repo = SmsRepository.get(this)

        binding.btnScanQr.setOnClickListener { scan() }
        binding.btnManual.setOnClickListener { showForm() }
        binding.btnConnect.setOnClickListener {
            connect(
                binding.inputSetupUrl.text?.toString()?.trim().orEmpty(),
                binding.inputSetupToken.text?.toString()?.trim().orEmpty(),
            )
        }
        binding.btnBack.setOnClickListener { showChoice() }
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (binding.groupManual.visibility == View.VISIBLE) showChoice() else finishAffinity()
            }
        })
    }

    private fun showChoice() {
        binding.groupChoice.visibility = View.VISIBLE
        binding.groupManual.visibility = View.GONE
        binding.resultText.text = ""
    }

    private fun showForm() {
        binding.groupChoice.visibility = View.GONE
        binding.groupManual.visibility = View.VISIBLE
        if (binding.inputSetupUrl.text.isNullOrEmpty()) binding.inputSetupUrl.setText(prefs.serverUrl)
        if (binding.inputSetupToken.text.isNullOrEmpty()) binding.inputSetupToken.setText(prefs.apiToken)
    }

    private fun scan() {
        scanner.launch(
            ScanOptions()
                .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                .setPrompt(getString(R.string.setup_scan_prompt))
                .setBeepEnabled(false)
                .setOrientationLocked(false)
        )
    }

    private fun onScanned(raw: String) {
        val setup = SetupQr.parse(raw)
        if (setup == null) {
            showChoice()
            binding.resultText.text = getString(R.string.setup_qr_invalid)
            return
        }
        showForm()
        binding.inputSetupUrl.setText(setup.serverUrl)
        binding.inputSetupToken.setText(setup.token)       // a password field: shown as dots
        connect(setup.serverUrl, setup.token)
    }

    private fun connect(url: String, token: String) {
        if (url.isBlank() || token.isBlank()) {
            binding.resultText.text = getString(R.string.settings_fill_both)
            return
        }
        prefs.serverUrl = url
        prefs.apiToken = token
        binding.btnConnect.isEnabled = false
        binding.btnScanQr.isEnabled = false
        binding.resultText.text = getString(R.string.settings_testing)
        lifecycleScope.launch {
            val result = repo.ping()
            binding.btnConnect.isEnabled = true
            binding.btnScanQr.isEnabled = true
            val body = result.getOrNull()
            if (body == null) {
                binding.resultText.text = getString(R.string.settings_test_fail, result.exceptionOrNull()?.message ?: "")
                return@launch
            }
            val device = body.device ?: ""
            val store = body.store?.takeIf { it.isNotBlank() }
            binding.resultText.text = if (store != null) getString(R.string.setup_connected_store, store, device)
            else getString(R.string.settings_test_ok, device)
            delay(1200)                                     // let the operator read which store / device it is
            finish()                                        // back to MainActivity, now configured
        }
    }
}
