// Exercise the public AMS RF MEL API against a real receiver worker.
#include <rfmel/admin/AdminMEL.h>
#include <rfmel/admin/StatusControl.h>
#include <rfmel/c2/C2MEL.h>
#include <rfmel/c2/JobDetail.h>
#include <rfmel/data/DataMEL.h>
#include <rfmel/data/ProductRxEndpoint.h>
#include <chrono>
#include <condition_variable>
#include <fstream>
#include <iostream>
#include <mutex>
#include <stdexcept>

extern "C" std::shared_ptr<ams::iface::rfmel::AdminMEL> createAdminMEL(std::string_view);
extern "C" std::shared_ptr<ams::iface::rfmel::C2MEL> createC2MEL(std::string_view);
extern "C" std::shared_ptr<ams::iface::rfmel::DataMEL> createDataMEL(std::string_view);

int main(int argc, char** argv) {
    if (argc != 3) return 2;
    namespace rf = ams::iface::rfmel;
    auto admin = createAdminMEL(argv[1]);
    if (!admin->getUCIControl()->getStatusControl()->commandState(ams::iface::mel::MFA_State::Operate))
        throw std::runtime_error("MEL operational command rejected");
    auto c2 = createC2MEL(argv[1]);
    auto data = createDataMEL(argv[1]);
    auto va = c2->requestVirtualAperture(0, 1, {}, "", {}).get().get();
    auto command = va->createElementGroupCommand("0");
    command->addExpectedCenterFrequencies(rf::FrequencyRange(24'125'000'000., 24'125'000'000.));
    command->setDesiredDutyFactor(1.0);
    rf::JobRequest request;
    request.addElementGroup(command);
    auto job = va->requestJob(request).get().get();
    job->finalize();
    auto endpoint = data->createProductRxEndpoint(rf::JobDataFormat::ComplexINT16, 512, nullptr).get().get();
    std::mutex mutex;
    std::condition_variable condition;
    bool received = false;
    std::function<void(std::shared_ptr<rf::ProductRxMetadata>, rf::JobDataPointer, size_t)> callback =
        [&](auto metadata, auto pointer, size_t count) {
            auto samples = std::get_if<rf::MELComplex<int16_t>*>(&pointer);
            if (!metadata || !samples || !*samples || count != 128) return;
            std::ofstream output(argv[2], std::ios::binary);
            for (size_t i = 0; i < count; ++i) {
                // Persist decoded callback values, rather than the original UDP bytes.
                const int16_t pair[] = {(*samples)[i].real(), (*samples)[i].imag()};
                output.write(reinterpret_cast<const char*>(pair), sizeof(pair));
            }
            output.close();
            std::lock_guard lock(mutex);
            received = true;
            condition.notify_one();
        };
    endpoint->setDataReadyCallback(callback);
    std::cout << "MEL_READY" << std::endl;
    std::unique_lock lock(mutex);
    if (!condition.wait_for(lock, std::chrono::seconds(10), [&] { return received; })) return 1;
    std::cout << "MEL_RECEIVED_128_COMPLEX_INT16" << std::endl;
    return 0;
}
